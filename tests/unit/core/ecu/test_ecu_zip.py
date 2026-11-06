import zipfile

import pytest

from ddt4all.core.ecu import ecu_zip


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


@pytest.fixture(autouse=True)
def fresh_cache():
    ecu_zip.clear_cache()
    yield
    ecu_zip.clear_cache()


def test_zip_is_opened_once(tmp_path, mocker):
    path = str(tmp_path / "ecu.zip")
    make_zip(path, {"a.json": "1"})
    opened = mocker.spy(zipfile, "ZipFile")

    first = ecu_zip.get_zip(path)
    second = ecu_zip.get_zip(path)
    ecu_zip.zip_names(path)

    assert first is second
    assert opened.call_count == 1
    assert first.read("a.json") == b"1"


def test_names_support_membership(tmp_path):
    path = str(tmp_path / "ecu.zip")
    make_zip(path, {"graphics/x.gif": "g", "db.json": "{}"})

    names = ecu_zip.zip_names(path)

    assert "graphics/x.gif" in names
    assert "graphics/y.gif" not in names


def test_reopens_when_archive_changes(tmp_path):
    path = str(tmp_path / "ecu.zip")
    make_zip(path, {"a.json": "old"})
    assert ecu_zip.get_zip(path).read("a.json") == b"old"

    make_zip(path, {"a.json": "new, longer content", "b.json": "2"})

    assert ecu_zip.get_zip(path).read("a.json") == b"new, longer content"
    assert "b.json" in ecu_zip.zip_names(path)


def test_missing_archive_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ecu_zip.get_zip(str(tmp_path / "nope.zip"))
