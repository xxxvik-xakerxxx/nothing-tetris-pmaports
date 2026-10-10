#!/usr/bin/env python3
"""Version faults and actual retained-resource lifecycle, without ELF execution."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from b41_mipc_init_resources import InitResources, inspect_resources, acquire
from b41_mipc_version_closure import matches, resolve


def symbol(name="service", version=None, undefined=False, kind="STT_FUNC"):
    return {"name": name, "version": version, "undefined": undefined, "type": kind,
            "binding": "STB_GLOBAL", "visibility": "STV_DEFAULT",
            "local_version": False, "hidden_version": False}


class VersionTests(unittest.TestCase):
    def test_version_and_owner_not_name_only(self):
        request = symbol(version={"name": "LIBC_N", "provider": "libc.so"}, undefined=True)
        provider = symbol(version={"name": "LIBC", "provider": "libc.so"})
        self.assertFalse(matches(request, provider, "libc.so"))
        provider["version"]["name"] = "LIBC_N"
        self.assertTrue(matches(request, provider, "libc.so"))
        self.assertFalse(matches(request, provider, "wrong-owner.so"))
        request["version"]["hash"] = 1
        provider["version"]["hash"] = 2
        self.assertFalse(matches(request, provider, "libc.so"))
        provider["version"]["hash"] = 1
        provider["visibility"] = "STV_HIDDEN"
        self.assertFalse(matches(request, provider, "libc.so"))

    def test_default_hidden_ifunc_and_object(self):
        request, provider = symbol(undefined=True), symbol(kind="STT_LOOS")
        self.assertTrue(matches(request, provider, "libc.so"))
        provider["hidden_version"] = True
        self.assertFalse(matches(request, provider, "libc.so"))
        provider["hidden_version"] = False
        request["type"] = "STT_OBJECT"
        self.assertFalse(matches(request, provider, "libc.so"))

    def test_missing_dependency_is_not_complete(self):
        data = {"libmipc.so": {"path": "/fixture", "sha256": "fixture",
                              "needed": ["liblog.so"], "symbols": []}}
        report = resolve(data)
        self.assertEqual(report["missing_libraries"], ["liblog.so"])
        self.assertFalse(report["versioned_symbol_closure_complete"])
        self.assertFalse(report["engine_readiness"])


@unittest.skipUnless(os.environ.get("TETRIS_B41_MIPC_VENDOR") and os.environ.get("TETRIS_BIONIC_ROOT"),
                     "actual vendor/Bionic assets not supplied")
class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.vendor = Path(os.environ["TETRIS_B41_MIPC_VENDOR"])
        self.bionic = Path(os.environ["TETRIS_BIONIC_ROOT"])

    def test_real_versions_and_retained_ownership(self):
        with inspect_resources(self.vendor, self.bionic) as lease:
            self.assertEqual(lease.report["missing_libraries"], ["liblog.so"])
            unresolved = lease.report["unresolved_required_symbols"]
            self.assertEqual({s["symbol"] for s in unresolved},
                             {"__android_log_buf_write", "__android_log_assert"})
            self.assertTrue(all(s["version"]["name"] == "LIBLOG" and
                                s["version"]["provider"] == "liblog.so"
                                for s in unresolved))
            self.assertIn("ld-android.so", lease.descriptors)
            self.assertTrue(lease.images["ld-android.so"]["path"].endswith("/bin/linker64"))
            fds = list(lease.descriptors.values())
            lease.validate_retained()
            with self.assertRaises(OSError) as result:
                lease.require_closure()
            self.assertEqual(result.exception.errno, errno.ENODATA)
        for fd in fds:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_actual_acquire_failure_closes_every_fd(self):
        closed = []
        original_close = os.close
        def tracked_close(fd):
            closed.append(fd)
            original_close(fd)
        with patch("b41_mipc_init_resources.os.close", side_effect=tracked_close):
            with self.assertRaises(OSError) as result:
                acquire(self.vendor, self.bionic)
        self.assertEqual(result.exception.errno, errno.ENODATA)
        self.assertEqual(len(closed), 9)
        for fd in closed:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_pin_symlink_fifo_faults_do_not_leave_descriptors(self):
        with InitResources() as lease:
            with self.assertRaises(OSError) as result:
                lease.add(self.vendor / "libmipc.so", "0" * 64)
            self.assertEqual(result.exception.errno, errno.EBADMSG)
            self.assertFalse(lease.descriptors)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link.so").symlink_to(self.vendor / "libmipc.so")
            os.mkfifo(root / "fifo.so")
            for path in (root / "link.so", root / "fifo.so"):
                with InitResources() as lease:
                    with self.assertRaises(OSError) as result:
                        lease.add(path, "0" * 64)
                    self.assertEqual(result.exception.errno, errno.EINVAL)
                    self.assertFalse(lease.descriptors)

    def test_duplicate_owner_and_mutation_rejected(self):
        with InitResources() as lease:
            lease.add(self.vendor / "libmipc.so",
                      "aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56")
            with self.assertRaises(OSError) as result:
                lease.add(self.vendor / "libmipc.so",
                          "aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56")
            self.assertEqual(result.exception.errno, errno.EEXIST)
            # Inject stale identity without mutating any real asset.
            lease.identities["libmipc.so"] = (0, 0, 0, 0, 0)
            with self.assertRaises(OSError) as result:
                lease.validate_retained()
            self.assertEqual(result.exception.errno, errno.ESTALE)


if __name__ == "__main__":
    unittest.main()
