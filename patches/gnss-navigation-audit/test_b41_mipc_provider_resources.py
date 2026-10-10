"""Actual pinned provider regression, never loading/executing ELF data."""
import errno
import fcntl
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock

from b41_mipc_provider_resources import acquire_providers, LoaderResources, LIBLOG_SHA, LAYOUT
from b41_mipc_init_resources import inspect_resources
from b41_mipc_version_closure import decode

STOCK = Path(os.environ.get("TETRIS_B41_STOCK_ROOT",
    "/private/tmp/tetris-b41-system-liblog-ci38039798135"))
BIONIC = Path(os.environ.get("TETRIS_BIONIC_ROOT",
    "/private/tmp/tetris-gnss-root-ci37898372984"))


class ProviderTests(unittest.TestCase):
    def test_validation_failure_preserves_first_over_cleanup(self):
        resources = SimpleNamespace(images={}, close=Mock(side_effect=OSError(errno.EIO, "close fault")))
        with patch("b41_mipc_provider_resources.acquire", return_value=resources):
            with self.assertRaises(OSError) as caught:
                acquire_providers(STOCK, BIONIC)
        self.assertEqual(caught.exception.errno, errno.ENODATA)
        self.assertIn("close fault", caught.exception.__notes__[0])

    def test_staging_failure_preserves_first_over_source_cleanup(self):
        resources = SimpleNamespace(report={}, close=Mock(side_effect=OSError(errno.EIO, "source close")))
        with patch("b41_mipc_provider_resources.acquire_providers", return_value=resources), \
                patch("b41_mipc_provider_resources.SealedStage", side_effect=OSError(errno.ENOMEM, "stage fault")):
            with self.assertRaises(OSError) as caught:
                LoaderResources(STOCK, BIONIC)
        self.assertEqual(caught.exception.errno, errno.ENOMEM)
        self.assertIn("source close", caught.exception.__notes__[0])

    def test_mode_failure_preserves_first_over_stage_cleanup(self):
        resources = SimpleNamespace(report={}, close=Mock())
        stage = SimpleNamespace(descriptors={"ld-android.so": 7},
            close=Mock(side_effect=OSError(errno.EIO, "stage close")))
        with patch("b41_mipc_provider_resources.acquire_providers", return_value=resources), \
                patch("b41_mipc_provider_resources.SealedStage", return_value=stage), \
                patch("b41_mipc_provider_resources.os.fchmod", side_effect=OSError(errno.EROFS, "mode fault")):
            with self.assertRaises(OSError) as caught:
                LoaderResources(STOCK, BIONIC)
        self.assertEqual(caught.exception.errno, errno.EROFS)
        self.assertIn("stage close", caught.exception.__notes__[0])

    def test_actual_complete_closure_and_exports(self):
        with acquire_providers(STOCK, BIONIC) as resources:
            report = resources.report
            self.assertTrue(report["versioned_symbol_closure_complete"])
            self.assertFalse(report["engine_readiness"])
            self.assertFalse(report["runtime_namespace_and_services_proven"])
            self.assertEqual(report["missing_libraries"], [])
            self.assertEqual(report["unresolved_required_symbols"], [])
            self.assertEqual(len(resources.images), 10)
            self.assertEqual(resources.images["liblog.so"]["sha256"], LIBLOG_SHA)
            for name in ("__android_log_buf_write", "__android_log_assert"):
                rows = [r for r in report["resolved_versioned_bindings"]
                        if r["consumer"] == "libmtkrillog.so" and r["symbol"] == name]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["providers"], ["liblog.so"])
                self.assertEqual(rows[0]["version"]["name"], "LIBLOG")

    def test_missing_genuine_provider_remains_refusal(self):
        with inspect_resources(STOCK / "vendor/lib64", BIONIC) as resources:
            self.assertEqual(resources.report["missing_libraries"], ["liblog.so"])
            with self.assertRaises(OSError) as caught:
                resources.require_closure()
            self.assertEqual(caught.exception.errno, errno.ENODATA)

    def test_no_caller_pin_or_ndk_fallback(self):
        with patch("b41_mipc_provider_resources.LIBLOG_SHA", "0" * 64):
            with self.assertRaises(OSError) as caught:
                acquire_providers(STOCK, BIONIC)
            self.assertEqual(caught.exception.errno, errno.EBADMSG)

    def test_c_mount_order_matches_producer(self):
        source = Path(__file__).with_name("b41_mipc_loader_root.c").read_text()
        cursor = source.index("static const char *const targets")
        for _, path in LAYOUT:
            cursor = source.index('"' + path + '"', cursor) + len(path) + 2
        self.assertNotIn("execve(", source)
        self.assertNotIn("dlopen(", source)

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux sealing required in CI")
    def test_actual_sealed_bytes_modes_transfer_and_close(self):
        owned = LoaderResources(STOCK, BIONIC)
        descriptors = owned.move()
        try:
            self.assertEqual(len(descriptors), 10)
            for index, (fd, (name, _)) in enumerate(zip(descriptors, LAYOUT)):
                data = os.pread(fd, os.fstat(fd).st_size, 0)
                image = decode(data, f"sealed:{name}")
                self.assertEqual(image["soname"], name)
                self.assertEqual(image["sha256"], owned.report["providers"][name]["sha256"])
                seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
                self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals, seals)
                self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o444 if index else 0o555)
                with self.assertRaises(OSError):
                    os.pwrite(fd, b"X", 0)
            with self.assertRaises(OSError):
                owned.move()
            owned.close()  # Moved FDs remain solely owned by this fixture.
            self.assertTrue(all(os.fstat(fd).st_size > 0 for fd in descriptors))
        finally:
            for fd in descriptors:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
