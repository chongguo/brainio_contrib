import datetime
import os
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
import pytest

import brainio_contrib
from brainio_contrib.packaging import package_stimulus_set, add_image_metadata_to_db, create_image_zip, \
    add_stimulus_set_metadata_and_lookup_to_db, package_data_assembly, write_netcdf
import brainio_collection
from brainio_collection.lookup import pwdb
from brainio_collection.knownfile import KnownFile as kf
from brainio_collection.stimuli import StimulusSetModel, ImageStoreModel, AttributeModel, ImageModel, \
    StimulusSetImageMap, ImageStoreMap, ImageMetaModel


def now():
    return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f")


@pytest.fixture
def transaction():
    with pwdb.atomic() as txn:
        yield txn
        txn.rollback()


@pytest.fixture
def proto_stim():
    image_dir = Path(__file__).parent / "images"
    csv_path = image_dir / "test_images.csv"
    proto = pd.read_csv(csv_path)
    proto["image_current_local_file_path"] = [image_dir / f for f in proto["image_current_relative_file_path"]]
    del proto["image_current_relative_file_path"]
    proto["image_id"] = [f"{iid}.{now()}" for iid in proto["image_id"]]
    proto[f"test_{now()}"] = [f"{iid}.{now()}" for iid in proto["image_id"]]
    return proto


@pytest.fixture
def example_data_array(proto_stim):
    assy_hvm = brainio_collection.get_assembly("dicarlo.Majaj2015")
    sub = assy_hvm.loc[:, assy_hvm["image_id"].isin(proto_stim["image_id"]), :]
    result = xr.DataArray(sub).reset_index("presentation")
    preserve = ['neuroid', 'time_bin', 'image_id', 'repetition']
    remove = [x for x in result.coords if x not in preserve]
    result = result.drop(remove)
    del result.attrs["stimulus_set"]
    # result = result.reset_index(["neuroid", "time_bin"])
    return result


def test_create_image_zip(proto_stim):
    target_zip_path = Path(__file__).parent / "test_images.zip"
    sha1 = create_image_zip(proto_stim, target_zip_path)
    with zipfile.ZipFile(target_zip_path, "r") as target_zip:
        infolist = target_zip.infolist()
        assert len(infolist) == 25
        for zi in infolist:
            print(zi.filename)
            print(len(zi.filename))
            assert zi.filename.endswith(".png")
            assert not zi.is_dir()
            assert len(zi.filename) == 44


def test_add_image_metadata_to_db(transaction, proto_stim):
    pwdb.connect(reuse_if_open=True)
    stim_set_model, created = StimulusSetModel.get_or_create(name=f"test_stimulus_set.{now()}")
    image_store_model, created = ImageStoreModel.get_or_create(location_type="test_loc_type", store_type="test_store_type",
                                                               location="test_loc", unique_name=f"test_store.{now()}",
                                                               sha1=f"foo.{now()}")
    add_image_metadata_to_db(proto_stim, stim_set_model, image_store_model)
    pw_query = ImageModel.select() \
        .join(StimulusSetImageMap) \
        .join(StimulusSetModel) \
        .where(StimulusSetModel.name == stim_set_model.name)
    print(f"Length of select query:  {len(pw_query)}")
    assert len(pw_query) == 25


def test_add_stimulus_set_metadata_and_lookup_to_db(transaction, proto_stim):
    stim_set_name = f"test_stimulus_set.{now()}"
    bucket_name = "brainio-temp"
    zip_file_name = "test_images.zip"
    image_store_unique_name = f"test_store.{now()}"
    target_zip_path = Path(__file__).parent / zip_file_name
    sha1 = create_image_zip(proto_stim, target_zip_path)
    stim_set_model = add_stimulus_set_metadata_and_lookup_to_db(proto_stim, stim_set_name, bucket_name,
                                                                zip_file_name, image_store_unique_name,
                                                                sha1)
    pw_query = ImageStoreModel.select() \
        .join(ImageStoreMap) \
        .join(ImageModel) \
        .join(StimulusSetImageMap) \
        .join(StimulusSetModel) \
        .where(StimulusSetModel.name == stim_set_model.name)
    assert len(pw_query) == 25


def test_package_stimulus_set(transaction, proto_stim):
    stim_set_name = "dicarlo.test." + now()
    test_bucket = "brainio-temp"
    stim_model = package_stimulus_set(proto_stim, stimulus_set_name=stim_set_name, bucket_name=test_bucket)
    assert stim_model
    assert stim_model.name == stim_set_name
    stim_set_fetched = brainio_collection.get_stimulus_set(stim_set_name)
    assert len(proto_stim) == len(stim_set_fetched)
    for image in proto_stim.itertuples():
        orig = image.image_current_local_file_path
        fetched = stim_set_fetched.get_image(image.image_id)
        assert os.path.basename(orig) == os.path.basename(fetched)
        kf_orig = kf(orig)
        kf_fetched = kf(fetched)
        assert kf_orig.sha1 == kf_fetched.sha1


def test_write_netcdf(example_data_array):
    target_netcdf_file = str(Path(__file__).parent / ("test_" + now() + ".nc"))
    example_netcdf_file = str(Path(__file__).parent / "test_data.nc")
    sha1 = write_netcdf(example_data_array, target_netcdf_file)
    assert sha1
    assert sha1 == kf(target_netcdf_file).sha1 == kf(example_netcdf_file).sha1


def test_add_data_assembly_lookup_to_db(transaction):
    assert False


def test_package_data_assembly(transaction):
    assy_model = package_data_assembly()
    assert assy_model
    assert False


