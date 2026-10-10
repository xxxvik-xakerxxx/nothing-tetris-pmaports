#!/usr/bin/env python3
"""Input checks only: no compiler, downloads or hardware access."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("kernel-object-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name)
        commit = "a" * 40
        self.archive = f"linux-postmarketos-mediatek-mt6878-{commit}.tar.gz"
        (self.package / smoke.CONFIG).write_text("# test config\n")
        (self.package / "0001-test.patch").write_text("test patch\n")
        sums = "\n".join(
            hashlib.sha512((self.package / name).read_bytes()).hexdigest() + "  " + name
            for name in [smoke.CONFIG, "0001-test.patch"])
        self.source = (
            f'_commit="{commit}"\nsource="\n'
            '$pkgname-$_commit.tar.gz::https://github.com/MT6878-mainline/$_repository/archive/$_commit.tar.gz\n'
            '$_config\n0001-test.patch\n0002-test.patch.vendor\n"\n'
            f'sha512sums="\n{sums}\n' + "0" * 128 + f'  {self.archive}\n"\n')

    def write(self, source=None):
        (self.package / "APKBUILD").write_text(source or self.source)

    def test_package_order_and_vendor_exclusion(self):
        self.write()
        plan = smoke.plan(self.package)
        self.assertEqual(plan["patches"], ["0001-test.patch"])
        self.assertEqual(plan["archive"], self.archive)

    def test_modified_patch_fails(self):
        self.write()
        (self.package / "0001-test.patch").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            smoke.plan(self.package)

    def test_duplicate_patch_fails(self):
        self.write(self.source.replace("$_config\n", "$_config\n0001-test.patch\n"))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            smoke.plan(self.package)

    def test_duplicate_checksum_fails(self):
        self.write(self.source.replace('sha512sums="\n', 'sha512sums="\n' + "0" * 128 + f"  {self.archive}\n"))
        with self.assertRaisesRegex(ValueError, "duplicate package checksum"):
            smoke.plan(self.package)

    def test_mutable_source_fails(self):
        self.write(self.source.replace("a" * 40, "main"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            smoke.plan(self.package)

    def test_unknown_archive_expression_fails(self):
        self.write(self.source.replace("https://github.com/MT6878-mainline", "https://example.invalid"))
        with self.assertRaisesRegex(ValueError, "archive expression"):
            smoke.plan(self.package)

    def test_real_package_inputs(self):
        plan = smoke.plan(Path(__file__).resolve().parents[1] / smoke.PACKAGE)
        self.assertGreater(len(plan["patches"]), 100)
        self.assertEqual(len(plan["objects"]), 6)

    def test_research_staging_preserves_bytes_without_shipping_wiring(self):
        root = Path(__file__).resolve().parents[1]
        parent = self.package / "drivers/soc/mediatek"
        parent.mkdir(parents=True)
        (parent / "Makefile").write_text("# original parent\n")
        provider = self.package / "drivers/memory/Makefile"
        provider.parent.mkdir(parents=True)
        provider.write_text("obj-$(CONFIG_MTK_SMI) += mtk-smi.o\n")
        smoke.stage_research_sources(self.package, root)
        for source, destination in smoke.RESEARCH_SOURCES.items():
            self.assertEqual((root / source).read_bytes(),
                             (self.package / destination).read_bytes())
        self.assertEqual((parent / "Makefile").read_text(), "# original parent\n")
        self.assertFalse((parent / "Kconfig").exists())
        self.assertEqual(len(smoke.RESEARCH_OBJECTS), 26)
        self.assertEqual(smoke.PROVIDER_OBJECTS, ("drivers/memory/mtk-smi.o",))
        self.assertEqual(provider.read_text(), "obj-$(CONFIG_MTK_SMI) += mtk-smi.o\n")
        self.assertTrue((self.package / smoke.RESEARCH_DIR / "Makefile").read_text().startswith("obj-y += "))
        for name in smoke.CAMERA_OBJECTS:
            makefile = self.package / Path(name).parent / "Makefile"
            self.assertIn(Path(name).name, makefile.read_text())
        self.assertNotIn("owner-kunit.o", (self.package / smoke.RESEARCH_DIR / "Makefile").read_text())

    def test_packaged_flat_consumer_matches_verified_source(self):
        root = Path(__file__).resolve().parents[1]
        package = root / smoke.PACKAGE
        patch_text = (package / "0120-misc-tetris-gpueb-authenticated-ram-analysis.patch").read_text()
        section = patch_text.split("+++ b/drivers/misc/gpueb-flat-analysis.c\n", 1)[1]
        header, *lines = section.splitlines()
        self.assertTrue(header.startswith("@@ -0,0 +1,"))
        self.assertTrue(all(line.startswith("+") for line in lines))
        consumer = "\n".join(line[1:] for line in lines) + "\n"
        self.assertEqual(consumer, (root / "patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c").read_text())
        self.assertIn("CONFIG_TETRIS_GPUEB_FLAT_ANALYSIS=m", (package / smoke.CONFIG).read_text())

    def camera_overlay_fixture(self):
        root = Path(__file__).resolve().parents[1]
        smoke.stage_research_sources(self.package, root)
        graph = self.package / smoke.CAMERA_GRAPH
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_bytes((root / "patches/camera-seninf/mt6878-seninf-graph.c").read_bytes())
        spec = importlib.util.spec_from_file_location("lifecycle", root / "patches/camera-seninf-controller/generate-lifecycle.py")
        lifecycle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lifecycle)
        sensor = self.package / "drivers/media/i2c/imx882-tetris-stream.c"
        sensor.parent.mkdir(parents=True)
        sensor.write_text(lifecycle.sensor_source())
        return root, graph, sensor

    def test_native_camera_overlays_keep_production_graph_target(self):
        root, graph, sensor = self.camera_overlay_fixture()
        smoke.stage_camera_overlays(self.package, root)
        self.assertIn("mt6878_seninf_pm_resume", graph.read_text())
        self.assertIn("imx882_enable_streams", sensor.read_text())
        destination = self.package / Path(next(iter(smoke.CAMERA_SOURCES.values()))).parent
        self.assertFalse((destination / graph.name).exists())
        self.assertIn("mt6878_native_capture_receiver_stop", (destination / "mt6878-camsv-platform.c").read_text())

    def test_failed_overlay_does_not_publish_partial_graph(self):
        root, graph, _ = self.camera_overlay_fixture()
        original = graph.read_text().replace('#include "mt6878-seninf-contract.h"', '#include "stale-contract.h"')
        graph.write_text(original)
        with self.assertRaises(smoke.subprocess.CalledProcessError):
            smoke.stage_camera_overlays(self.package, root)
        self.assertEqual(graph.read_text(), original)
        destination = self.package / Path(next(iter(smoke.CAMERA_SOURCES.values()))).parent
        self.assertFalse((destination / graph.name).exists())

    def test_research_collision_fails_before_copying_other_sources(self):
        root = Path(__file__).resolve().parents[1]
        destinations = list(smoke.RESEARCH_SOURCES.values())
        existing = self.package / destinations[-1]
        existing.parent.mkdir(parents=True)
        existing.write_text("original\n")
        with self.assertRaisesRegex(ValueError, "already exists"):
            smoke.stage_research_sources(self.package, root)
        self.assertFalse((self.package / destinations[0]).exists())
        self.assertEqual(existing.read_text(), "original\n")

    def test_research_makefile_collision_is_not_overwritten(self):
        root = Path(__file__).resolve().parents[1]
        existing = self.package / smoke.RESEARCH_DIR / "Makefile"
        existing.parent.mkdir(parents=True)
        existing.write_text("# preserve\n")
        with self.assertRaisesRegex(ValueError, "already exists"):
            smoke.stage_research_sources(self.package, root)
        self.assertEqual(existing.read_text(), "# preserve\n")
        self.assertFalse((self.package / next(iter(smoke.RESEARCH_SOURCES.values()))).exists())

    def test_thin_lto_object_identity(self):
        target = self.package / "unit.o"
        for magic in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
            target.write_bytes(magic)
            with patch.object(smoke.subprocess, "check_output", return_value=
                              'target triple = "aarch64-unknown-linux-gnu"\n') as check:
                self.assertEqual(smoke.object_identity(target)["format"], "LLVM bitcode")
                self.assertEqual(check.call_args.args[0][0], "llvm-dis")
            for ir in ('target triple = "x86_64-unknown-linux-gnu"\n', "",
                       'target triple = "aarch64-linux"\ntarget triple = "aarch64-linux"\n'):
                with patch.object(smoke.subprocess, "check_output", return_value=ir):
                    with self.assertRaisesRegex(ValueError, "bitcode architecture"):
                        smoke.object_identity(target)

    def test_elf_object_identity(self):
        target = self.package / "unit.o"
        target.write_bytes(b"\x7fELF")
        with patch.object(smoke.subprocess, "check_output", return_value="Machine: AArch64\n"):
            self.assertEqual(smoke.object_identity(target)["machine"], "AArch64")
        for header in ("Machine: X86-64\n", ""):
            with patch.object(smoke.subprocess, "check_output", return_value=header):
                with self.assertRaisesRegex(ValueError, "object architecture"):
                    smoke.object_identity(target)

    def test_unknown_magic_cannot_be_blessed_by_header(self):
        target = self.package / "unit.o"
        target.write_bytes(b"nope")
        with patch.object(smoke.subprocess, "check_output", return_value="Machine: AArch64\n"):
            with self.assertRaisesRegex(ValueError, "object architecture"):
                smoke.object_identity(target)


if __name__ == "__main__":
    unittest.main()
