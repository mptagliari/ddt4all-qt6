"""Shared, lazily opened handle on the ECU database archive (ecu.zip).

Opening a ZipFile parses the whole central directory (~12k entries, roughly
90 ms in pure Python), so doing it for every ECU, layout or picture made the
UI sluggish. The archive is opened once and reused; it is reopened when the
file changes on disk (e.g. after a database conversion).
"""
import os
import threading
import zipfile

ECU_ZIP = "ecu.zip"

_lock = threading.Lock()
_cache = {}  # path -> (stamp, ZipFile, frozenset of member names)


def _stamp(path):
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size


def _entry(path):
    stamp = _stamp(path)
    with _lock:
        cached = _cache.get(path)
        if cached and cached[0] == stamp:
            return cached
        if cached:
            cached[1].close()
        zf = zipfile.ZipFile(path, mode='r')
        entry = (stamp, zf, frozenset(zf.namelist()))
        _cache[path] = entry
        return entry


def get_zip(path=ECU_ZIP):
    """Shared ZipFile for path. Do not close it."""
    return _entry(path)[1]


def zip_names(path=ECU_ZIP):
    """Set of member names of path (O(1) membership tests)."""
    return _entry(path)[2]


def clear_cache():
    with _lock:
        for _stamp_, zf, _names in _cache.values():
            zf.close()
        _cache.clear()
