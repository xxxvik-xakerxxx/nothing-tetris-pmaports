#!/usr/bin/env python3
"""Actual read-only init-resource lease, retaining same-descriptor ELF bytes.

No loader/phone/init calls. Acquisition fails closed if versioned closure is
incomplete. Parent may consume owned descriptors only in its legitimate loader
handoff; this is not authority to launch init or to clear engine startup gates.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat

from b41_mipc_version_closure import decode, resolve

VENDOR_PINS = {
    "libmipc.so": "aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56",
    "libmtkrillog.so": "aa057f4d00d1968c93eee3accb30866175d01297ebfdda81dcba8e40b4d342d6",
    "libtrm.so": "0cc93d3c3a8b9343bcc45ee1ea37dafd1b6b04c7e7d4bf1921fec5140385da68",
    "libmtkproperty.so": "74c68447636c4676bac8054f337111d75d946441a233c06f539985fec4fe3f01",
}
PLATFORM = {
    "apex/com.android.runtime/bin/linker64": "4a8dd94eb2d0e59184247892ba5232f7dcbe88eb8c5a43e3a9e4c9c4d4ba7844",
    "apex/com.android.runtime/lib64/bionic/libc.so": "1e365bc2da9ca1e830801ce49f389e6e7fcbc0be7d82824924026af8751f8648",
    "apex/com.android.runtime/lib64/bionic/libm.so": "25c852fca54f103e1a8ac2785a51ef2db2ea21ae9a89295d156ec63cbeb90e40",
    "apex/com.android.runtime/lib64/bionic/libdl.so": "ec8a5f55630b6b41ad94b8bbdc6da308e36903709ce759bf2a3a59640715ae32",
    "system/lib64/libc++.so": "2267f93b8b3c9d1967f1833d5f71c7312213c43bb291250cf772800763037fb9",
}


class InitResources:
    def __init__(self):
        self.descriptors = {}
        self.images = {}
        self.identities = {}
        self.report = None

    def add(self, path, pin):
        entry = os.lstat(path)
        if not stat.S_ISREG(entry.st_mode):
            raise OSError(errno.EINVAL, "regular provider path required", str(path))
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if self.identity(entry) != self.identity(before):
                raise OSError(errno.ESTALE, "provider path replaced before open", str(path))
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 64 * 1024 * 1024:
                raise OSError(errno.EINVAL, "regular bounded provider required", str(path))
            data = bytearray()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > before.st_size:
                    raise OSError(errno.ESTALE, "provider grew while hashing", str(path))
            after = os.fstat(fd)
            if self.identity(before) != self.identity(after) or len(data) != before.st_size:
                raise OSError(errno.ESTALE, "provider changed while hashing", str(path))
            if hashlib.sha256(data).hexdigest() != pin:
                raise OSError(errno.EBADMSG, "provider SHA256 mismatch", str(path))
            image = decode(bytes(data), path)
            name = image["soname"]
            if name in self.images:
                raise OSError(errno.EEXIST, "ambiguous SONAME owner", name)
            os.lseek(fd, 0, os.SEEK_SET)
            self.images[name] = image
            self.descriptors[name] = fd
            self.identities[name] = self.identity(after)
            fd = -1
        finally:
            if fd >= 0:
                os.close(fd)

    @staticmethod
    def identity(value):
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns

    def validate_retained(self):
        for name, fd in self.descriptors.items():
            if self.identity(os.fstat(fd)) != self.identities[name]:
                raise OSError(errno.ESTALE, "retained provider changed", name)

    def require_closure(self):
        self.validate_retained()
        self.report = resolve(self.images)
        if not self.report["versioned_symbol_closure_complete"]:
            raise OSError(errno.ENODATA, "incomplete versioned init-resource closure")
        return self

    def close(self):
        errors = []
        for fd in self.descriptors.values():
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error)
        self.descriptors.clear()
        if errors:
            raise errors[0]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def inspect_resources(vendor_lib64, bionic_root, additional=()):
    lease = InitResources()
    try:
        for name, pin in VENDOR_PINS.items():
            lease.add(vendor_lib64 / name, pin)
        for relative, pin in PLATFORM.items():
            lease.add(bionic_root / relative, pin)
        for path, pin in additional:
            lease.add(path, pin)
        lease.report = resolve(lease.images)
        return lease
    except BaseException as error:
        try:
            lease.close()
        except OSError as cleanup_error:
            error.add_note(f"resource cleanup also failed: {cleanup_error}")
        raise


def acquire(vendor_lib64, bionic_root, additional=()):
    """Init handoff API: no caller boolean can bypass the closure check."""
    lease = inspect_resources(vendor_lib64, bionic_root, additional)
    try:
        return lease.require_closure()
    except BaseException as error:
        try:
            lease.close()
        except OSError as cleanup_error:
            error.add_note(f"resource cleanup also failed: {cleanup_error}")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-lib64", type=Path, required=True)
    parser.add_argument("--bionic-root", type=Path, required=True)
    parser.add_argument("--provider", nargs=2, action="append", default=[], metavar=("FILE", "SHA256"))
    args = parser.parse_args()
    # CLI is audit-only: incomplete resources are never exposed as a valid lease.
    with inspect_resources(args.vendor_lib64, args.bionic_root,
                           [(Path(p), h) for p, h in args.provider]) as lease:
        print(json.dumps(lease.report, sort_keys=True, indent=2))
        return 0 if lease.report["versioned_symbol_closure_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
