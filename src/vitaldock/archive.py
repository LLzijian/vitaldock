"""Bounded input readers. ZIP members are read in memory, never extracted."""

import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_FILES = 10000


class InputError(ValueError):
    pass


def inputs(source):
    path = Path(source).expanduser()
    if _link(path):
        raise InputError("symlink inputs are not supported")
    if path.is_dir():
        count = 0
        total = 0
        for current, directories, filenames in os.walk(path, followlinks=False, onerror=_walk_error):
            directories.sort()
            for directory in directories:
                if _link(Path(current) / directory):
                    raise InputError("symlink paths are not supported")
            for filename in sorted(filenames):
                if not filename.lower().endswith(".json"):
                    continue
                item = Path(current) / filename
                if _link(item) or not stat.S_ISREG(item.stat().st_mode):
                    raise InputError("only regular JSON files are supported")
                count += 1
                if count > MAX_FILES:
                    raise InputError("too many JSON files")
                data = _read_file(item)
                total += len(data)
                _size(len(data), total)
                yield item.relative_to(path).as_posix(), data
        if not count:
            raise InputError("no JSON files found; select the decrypted Huawei export folder")
    elif path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES:
                raise InputError("too many ZIP members")
            total = 0
            seen = set()
            for info in members:
                name = info.filename.replace("\\", "/")
                parts = PurePosixPath(name)
                if parts.is_absolute() or ".." in parts.parts or ":" in name:
                    raise InputError("unsafe ZIP member name")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise InputError("symlink ZIP members are not supported")
                if info.is_dir() or not name.lower().endswith(".json"):
                    continue
                if name in seen:
                    raise InputError("duplicate ZIP member name")
                seen.add(name)
                total += info.file_size
                _size(info.file_size, total)
                if info.flag_bits & 1:
                    raise InputError("encrypted ZIP: decrypt locally with 7-Zip, then import the folder")
                with archive.open(info) as handle:
                    data = handle.read(MAX_FILE + 1)
                _size(len(data), total)
                yield name, data
            if not seen:
                raise InputError("no JSON files found in ZIP")
    elif path.is_file() and path.suffix.lower() == ".json":
        yield path.name, _read_file(path)
    else:
        raise InputError("expected a JSON file, decrypted export folder, or unencrypted ZIP")


def _read_file(path):
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE + 1)
    _size(len(data), len(data))
    return data


def _size(size, total):
    if size > MAX_FILE or total > MAX_TOTAL:
        raise InputError("input size limit exceeded (64 MiB/file, 1 GiB/import)")


def _link(path):
    if path.is_symlink():
        return True
    if os.name == "nt" and path.exists():
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def _walk_error(error):
    raise error
