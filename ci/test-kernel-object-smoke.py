#!/usr/bin/env python3
"""Input checks only: no compiler, downloads or hardware access."""

import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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
        self.assertEqual(len(plan["objects"]), 7)
        self.assertEqual(plan["dtbs"], smoke.DTBS)

    def test_imx882_identity_uses_packaged_source_and_strict_application(self):
        package = Path(__file__).resolve().parents[1] / smoke.PACKAGE
        plan = smoke.plan(package)
        name = "0121-media-i2c-imx882-acquire-mclk-source.patch"
        driver = "drivers/media/i2c/imx882-identity.o"
        self.assertEqual(plan["patches"].count(name), 1)
        self.assertEqual(plan["patches"][-1], name)
        self.assertIn(name, smoke.STRICT_PATCHES)
        self.assertEqual(plan["objects"].count(driver), 1)
        self.assertIn("VIDEO_IMX882_IDENTITY", plan["module_options"])
        self.assertNotIn(driver, smoke.RESEARCH_OBJECTS + smoke.PROVIDER_OBJECTS)
        for prerequisite in ("0049-media-i2c-imx882-identity.patch",
                             "0050-media-i2c-imx882-honor-active-low-reset.patch",
                             "0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch",
                             "0106-media-i2c-imx882-check-shutdown.patch",
                             "0107-media-i2c-imx882-hold-clock-rate.patch"):
            self.assertLess(plan["patches"].index(prerequisite), plan["patches"].index(name))
        canonical = package.parents[3] / "patches/camera-camisp/activation/sensor-mclk.patch"
        self.assertEqual((package / name).read_bytes(), canonical.read_bytes())

    def test_imx882_identity_config_is_isolated_and_shipping_stays_disabled(self):
        for research in (False, True):
            command = smoke.config_options(Path("kernel"), Path("objects"), research)
            enabled = [command[i + 1] for i, flag in enumerate(command) if flag == "-e"]
            modules = [command[i + 1] for i, flag in enumerate(command) if flag == "-m"]
            for symbol in ("I2C", "OF", "GPIOLIB", "COMMON_CLK", "REGULATOR", "PINCTRL"):
                self.assertEqual(enabled.count(symbol), 1)
            self.assertEqual(modules.count("VIDEO_IMX882_IDENTITY"), 1)
        package = Path(__file__).resolve().parents[1] / smoke.PACKAGE
        config = (package / smoke.CONFIG).read_text()
        self.assertNotRegex(config, r"(?m)^CONFIG_VIDEO_IMX882_IDENTITY=(y|m)$")
        source = (package / "APKBUILD").read_text()
        self.assertIn("IMX882 identity probe must stay disabled in the shipped kernel", source)
        patch = (package / "0121-media-i2c-imx882-acquire-mclk-source.patch").read_text()
        self.assertNotRegex(patch, r'(?m)^\+[^+].*status\s*=\s*"okay"', msg="identity delta must not activate DT")

    def test_gnss_compiler_uses_reviewed_stack_and_real_kbuild(self):
        source = inspect.getsource(smoke.compile_gnss_tx)
        preparation = inspect.getsource(smoke.prepare_gnss_tx_sources)
        application = inspect.getsource(smoke.apply_gnss_tx)
        contract = json.loads((Path(__file__).resolve().parents[1] /
                               "patches/gnss/write-boundary/STAGING.json").read_text())
        self.assertIn('plan["stacked_source_sha512"]', preparation)
        self.assertEqual(len(contract["stacked_source_sha512"]), 4)
        self.assertIn('plan["patch_sha512"]', preparation)
        self.assertIn('stage.transform(name', application)
        self.assertIn('prepare_gnss_tx_sources(work)', source)
        self.assertIn('apply_gnss_tx(stage, vendor)', source)
        self.assertIn('"CONFIG_MTK_GPS_SUPPORT=y"', source)
        self.assertIn('("gps_each_link.o", "linux/gps_each_device.o")', source)
        self.assertLess(source.index('"olddefconfig"'), source.index('"modules_prepare"'))
        self.assertNotIn('"modules"]', source)
        self.assertNotIn("KBUILD_MODPOST_WARN", source)
        self.assertNotIn("KCFLAGS=-I", source)

    def test_real_dtbs_compiled_validated_and_retained(self):
        output = self.package / "objects"
        report = self.package / "evidence"
        for name in smoke.DTBS:
            dtb = output / "arch/arm64/boot/dts" / name
            dtb.parent.mkdir(parents=True, exist_ok=True)
            dtb.write_bytes(name.encode())
        make = ["make", "ARCH=arm64", "LLVM=1"]
        with patch.object(smoke, "run") as run:
            hashes = smoke.compile_dtbs(make, output, report)
        self.assertEqual(run.call_args_list[0].args[0], [*make, *smoke.DTBS])
        self.assertEqual(run.call_count, 1 + len(smoke.DTBS))
        self.assertEqual(set(hashes), set(smoke.DTBS))
        for name in smoke.DTBS:
            self.assertEqual(hashes[name], hashlib.sha256(name.encode()).hexdigest())
            self.assertEqual((report / "dtbs" / Path(name).name).read_bytes(), name.encode())

    def test_camera_fixture_is_validated_and_never_a_boot_input(self):
        output = self.package / "objects"
        report = self.package / "evidence"
        report.mkdir()
        board = smoke.CAMISP_RESOURCE_PLAN["diagnostic_board"]
        dtb = output / "arch/arm64/boot/dts" / board["target"]
        dtb.parent.mkdir(parents=True)
        dtb.write_bytes(b"synthetic fixture capture")
        with patch.object(smoke, "run") as run:
            outcome = smoke.compile_camisp_resource_dtb(["make"], output, report)
        self.assertEqual(run.call_args_list[0].args[0], ["make", board["target"]])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ["--fixture", dtb])
        self.assertFalse(outcome["install_allowed"])
        self.assertFalse((report / "dtbs").exists())
        self.assertEqual((report / "nonbootable-dtbs" / dtb.name).read_bytes(), dtb.read_bytes())

    def test_camera_fixture_validation_failure_is_not_published(self):
        output = self.package / "objects"
        report = self.package / "evidence"
        report.mkdir()
        dtb = output / "arch/arm64/boot/dts" / smoke.CAMISP_RESOURCE_PLAN["diagnostic_board"]["target"]
        dtb.parent.mkdir(parents=True)
        dtb.write_bytes(b"synthetic rejected fixture")
        with patch.object(smoke, "run", side_effect=[None, subprocess.CalledProcessError(1, "validator")]):
            with self.assertRaises(subprocess.CalledProcessError):
                smoke.compile_camisp_resource_dtb(["make"], output, report)
        self.assertFalse((report / "nonbootable-dtbs").exists())
        self.assertEqual((report / "unvalidated-nonbootable-dtbs" / dtb.name).read_bytes(), dtb.read_bytes())

    def test_supplier_dt_variants_never_enter_install_inputs(self):
        output = self.package / "objects"
        report = self.package / "evidence"
        for name in ("candidate", "blocked_ownership"):
            dtb = output / "arch/arm64/boot/dts" / smoke.CAMISP_SUPPLIER_PLAN[name]["target"]
            dtb.parent.mkdir(parents=True, exist_ok=True)
            dtb.write_bytes(name.encode())
        with patch.object(smoke, "run") as run:
            result = smoke.compile_camisp_supplier_dtbs(["make"], output, report)
        self.assertEqual(run.call_count, 4)
        self.assertFalse((report / "dtbs").exists())
        self.assertEqual(set(result), {"candidate", "blocked_ownership"})
        for name, value in result.items():
            self.assertFalse(value["install_allowed"])
            self.assertFalse(value["hardware_activated"])

    def test_rejected_supplier_dt_preserves_raw_evidence_only(self):
        output = self.package / "objects"
        report = self.package / "evidence"
        dtb = output / "arch/arm64/boot/dts" / smoke.CAMISP_SUPPLIER_PLAN["candidate"]["target"]
        dtb.parent.mkdir(parents=True)
        dtb.write_bytes(b"rejected candidate")
        with patch.object(smoke, "run", side_effect=[None, subprocess.CalledProcessError(1, "validator")]):
            with self.assertRaises(subprocess.CalledProcessError):
                smoke.compile_camisp_supplier_dtbs(["make"], output, report)
        self.assertEqual((report / "unvalidated-supplier-dtbs" / dtb.name).read_bytes(), dtb.read_bytes())
        self.assertFalse((report / "dormant-supplier-dtbs").exists())
        self.assertFalse((report / "dtbs").exists())

    def test_missing_dtb_stops_smoke(self):
        with patch.object(smoke, "run"):
            with self.assertRaisesRegex(ValueError, "missing compiled DTB"):
                smoke.compile_dtbs(["make"], self.package, self.package / "evidence")

    def test_hif_dt_is_compiled_and_checked_without_changing_normal_dts(self):
        kernel = self.package / "kernel"
        sources = kernel / "arch/arm64/boot/dts/mediatek"
        sources.mkdir(parents=True)
        normal_source = sources / "mt6878-nothing-tetris-native.dts"
        normal_source.write_text("// shipping native source\n")
        output = self.package / "objects"
        dtb = output / "arch/arm64/boot/dts" / smoke.HIF_DTB
        dtb.parent.mkdir(parents=True)
        dtb.write_bytes(b"checked HIF fixture")
        report = self.package / "report"
        (report / "dtbs").mkdir(parents=True)
        with patch.object(smoke, "run") as run:
            result = smoke.compile_hif_dtb(["make", "ARCH=arm64"], kernel, output, report)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ["make", "ARCH=arm64", smoke.HIF_DTB])
        self.assertIn("patches/modem/drafts/runtime-hif-dt/check.py", run.call_args_list[1].args[0])
        self.assertEqual(normal_source.read_text(), "// shipping native source\n")
        self.assertEqual((report / "dtbs" / dtb.name).read_bytes(), dtb.read_bytes())
        self.assertEqual(result["dtb_sha256"], hashlib.sha256(dtb.read_bytes()).hexdigest())

    def test_research_requests_every_cam_main_dependency(self):
        command = smoke.config_options(Path("kernel"), Path("objects"), True)
        enabled = [command[i + 1] for i, value in enumerate(command) if value == "-e"]
        for symbol in (*smoke.CAM_MAIN_ENABLE, *smoke.CAM_MAIN_REACHABLE):
            self.assertIn(symbol, enabled)
        self.assertEqual(len(enabled), len(set(enabled)))
        normal = smoke.config_options(Path("kernel"), Path("objects"), False)
        self.assertNotIn("COMMON_CLK_MT6878_CAM", normal)

    def test_dt_only_never_builds_driver_objects_or_links_kernel(self):
        kernel = self.package / "kernel"
        work = self.package / "work"
        work.mkdir()
        report = self.package / "report"
        (report / "dtbs").mkdir(parents=True)
        with patch.object(smoke, "run") as run, \
                patch.object(smoke, "compile_dtbs", return_value={"native": "hash"}) as dt, \
                patch.object(smoke, "compile_hif_dtb", return_value={"dtb_sha256": "hif"}) as hif:
            result = smoke.compile_dt_only(kernel, self.package, work, report, {"objects": ["driver.o"]})
        self.assertEqual(result["objects"], [])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], "olddefconfig")
        dt.assert_called_once()
        hif.assert_called_once()

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
        self.assertEqual(len(smoke.RESEARCH_OBJECTS), 44)
        self.assertEqual(smoke.PROVIDER_OBJECTS, (
            "drivers/memory/mtk-smi.o", "drivers/clk/mediatek/clk-mt6878-cam.o",
            "drivers/iommu/mtk_iommu.o"))
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

    def test_infra_clock_staging_does_not_replace_parent_kbuild_or_shipping_dt(self):
        root = Path(__file__).resolve().parents[1]
        parent = self.package / "drivers/clk/mediatek"
        parent.mkdir(parents=True)
        (parent / "Makefile").write_text("# original clock provider targets\n")
        dt = self.package / "arch/arm64/boot/dts/mediatek/mt6878.dtsi"
        dt.parent.mkdir(parents=True)
        dt.write_text("// original shipping DT\n")
        smoke.stage_research_sources(self.package, root)
        directory = self.package / smoke.INFRA_CLOCK_DIR
        self.assertEqual((parent / "Makefile").read_text(), "# original clock provider targets\n")
        self.assertEqual((directory / "Makefile").read_text(),
                         "obj-y += clk-mt6878-infra-ao.o\n"
                         "ccflags-y += -I$(srctree)/drivers/clk/mediatek\n")
        self.assertIn(smoke.INFRA_CLOCK_DIR + "/clk-mt6878-infra-ao.o", smoke.RESEARCH_OBJECTS)
        self.assertNotIn(smoke.INFRA_CLOCK_DIR + "/clk-mt6878-infra-ao.o", smoke.OBJECTS)
        self.assertIn("drivers/clk/mediatek", smoke.research_compile_flags(self.package))
        self.assertEqual(dt.read_text(), "// original shipping DT\n")

    def test_camisp_objects_and_config_are_isolated(self):
        for name in smoke.CAMISP_OBJECTS:
            self.assertIn(name, smoke.RESEARCH_OBJECTS + smoke.PROVIDER_OBJECTS)
            self.assertNotIn(name, smoke.OBJECTS)
        self.assertEqual(smoke.PROVIDER_OBJECTS.count("drivers/memory/mtk-smi.o"), 1)
        options = smoke.config_options(Path("kernel"), Path("objects"), True)
        for symbol in smoke.CAMISP_ENABLE:
            self.assertIn(symbol, options)
        source = Path(__file__).with_name("kernel-object-smoke.py").read_text()
        self.assertIn("repeat_consumers + CAMISP_OBJECTS", source)
        self.assertIn('manifest["camisp_kunit_disabled_objects"]', source)

    def test_camisp_resources_staging_preserves_clock_parent_and_dt_wiring(self):
        root = Path(__file__).resolve().parents[1]
        parent = self.package / "drivers/clk/mediatek"
        parent.mkdir(parents=True)
        for name in ("Makefile", "Kconfig"):
            (parent / name).write_text("# original clock parent\n")
        dts = self.package / "arch/arm64/boot/dts/mediatek"
        dts.mkdir(parents=True)
        (dts / "Makefile").write_text("# original DT targets\n")
        smoke.stage_research_sources(self.package, root)
        for name in ("Makefile", "Kconfig"):
            self.assertEqual((parent / name).read_text(), "# original clock parent\n")
        self.assertEqual((dts / "Makefile").read_text(), "# original DT targets\n")
        for source, destination in smoke.CAMISP_RESOURCE_PLAN["sources"].items():
            self.assertEqual((self.package / destination).read_bytes(), (root / source).read_bytes())
        for name in smoke.CAMISP_RESOURCE_OBJECTS:
            self.assertIn(name, smoke.RESEARCH_OBJECTS)
            self.assertNotIn(name, smoke.OBJECTS + smoke.PROVIDER_OBJECTS)
            makefile = self.package / Path(name).parent / "Makefile"
            self.assertEqual(makefile.read_text(), "obj-y += " + Path(name).name + "\n")

    def test_camisp_resources_require_native_dependencies_only_in_research_config(self):
        research = smoke.config_options(Path("kernel"), Path("objects"), True)
        normal = smoke.config_options(Path("kernel"), Path("objects"), False)
        for symbol in (*smoke.CAMISP_RESOURCE_ENABLE, *smoke.CAMISP_RESOURCE_REACHABLE):
            self.assertIn(symbol, research)
        self.assertNotIn("COMMON_CLK_MEDIATEK", normal)
        self.assertEqual(smoke.CAMISP_RESOURCE_PLAN["config_variants"], [{"KUNIT": "y"}, {"KUNIT": "n"}])
        source = Path(__file__).with_name("kernel-object-smoke.py").read_text()
        self.assertIn('manifest["camisp_resource_kunit_disabled_objects"]', source)
        self.assertIn("CAMISP_RESOURCE_OBJECTS + CAMISP_POWER_OBJECTS)", source)
        self.assertIn("(*CAMISP_ENABLE, *CAMISP_RESOURCE_ENABLE, *CAMISP_POWER_ENABLE)", source)

    def test_camisp_power_staging_and_include_are_isolated(self):
        root = Path(__file__).resolve().parents[1]
        parent = self.package / "drivers/pmdomain/mediatek"
        parent.mkdir(parents=True)
        for name in ("Makefile", "Kconfig", "mtk-pm-domains.c"):
            (parent / name).write_text("# original power provider\n")
        smoke.stage_research_sources(self.package, root)
        for name in ("Makefile", "Kconfig", "mtk-pm-domains.c"):
            self.assertEqual((parent / name).read_text(), "# original power provider\n")
        for source, destination in smoke.CAMISP_POWER_PLAN["sources"].items():
            self.assertEqual((self.package / destination).read_bytes(), (root / source).read_bytes())
        for name in smoke.CAMISP_POWER_OBJECTS:
            self.assertIn(name, smoke.RESEARCH_OBJECTS)
            self.assertNotIn(name, smoke.OBJECTS + smoke.PROVIDER_OBJECTS)
            makefile = self.package / Path(name).parent / "Makefile"
            self.assertEqual(makefile.read_text(), "obj-y += " + Path(name).name +
                             "\nccflags-y += -I$(srctree)/drivers/pmdomain/mediatek\n")
        source = Path(__file__).with_name("kernel-object-smoke.py").read_text()
        self.assertIn('manifest["camisp_power_kunit_disabled_objects"]', source)

    def test_camisp_power_manifest_rejects_provider_and_activation_drift(self):
        root = Path(__file__).resolve().parents[1]
        original = json.loads((root / smoke.CAMISP_POWER_MANIFEST).read_text())
        for field, value in (("runtime_activation", "enabled"),
                             ("include_directory", "drivers/other")):
            data = dict(original, **{field: value})
            with patch.object(smoke.json, "loads", return_value=data), self.assertRaises(ValueError):
                smoke.camisp_power_staging(root)
        data = dict(original, sources={"any": "drivers/pmdomain/mediatek/mtk-pm-domains.c"})
        with patch.object(smoke.json, "loads", return_value=data), self.assertRaises(ValueError):
            smoke.camisp_power_staging(root)

    def test_shared_supplier_payload_identity_and_generated_makefile(self):
        root = Path(__file__).resolve().parents[1]
        parent = self.package / "drivers/pmdomain/mediatek"
        parent.mkdir(parents=True)
        for name in ("Makefile", "Kbuild", "Kconfig", "mtk-pm-domains.c"):
            (parent / name).write_text("# retained parent\n")
        smoke.stage_research_sources(self.package, root)
        for name in ("Makefile", "Kbuild", "Kconfig", "mtk-pm-domains.c"):
            self.assertEqual((parent / name).read_text(), "# retained parent\n")
        sources = {**smoke.CAMISP_POWER_PLAN["sources"], **smoke.CAMISP_SHARED_SOURCES}
        self.assertEqual(len(sources), 4)
        for source, destination in sources.items():
            payload = (self.package / destination).read_bytes()
            self.assertEqual(payload, (root / source).read_bytes())
            self.assertEqual(hashlib.sha256(payload).hexdigest(),
                             smoke.CAMISP_SHARED_PLAN["source_sha256"][source])
            self.assertEqual(list(smoke.RESEARCH_SOURCES.values()).count(destination), 1)
        for name in (*smoke.CAMISP_POWER_OBJECTS, *smoke.CAMISP_SHARED_OBJECTS):
            self.assertEqual(smoke.RESEARCH_OBJECTS.count(name), 1)
            self.assertNotIn(name, smoke.OBJECTS + smoke.PROVIDER_OBJECTS)
            self.assertFalse((self.package / Path(name).parent / "Kbuild").exists())
        self.assertNotIn("patches/camera-camisp/power/Kbuild.shared", smoke.RESEARCH_SOURCES)
        makefile = self.package / smoke.CAMISP_SHARED_DIR / "Makefile"
        self.assertEqual(makefile.read_text(),
                         "obj-y += mt6878-vmm-supplier.o\n"
                         "ccflags-y += -I$(srctree)/drivers/pmdomain/mediatek "
                         "-I$(srctree)/drivers/pmdomain/mediatek/tetris-cam-power-smoke\n")

    def test_direct_object_flags_include_shared_leaf_headers(self):
        kernel = Path("/tmp/kernel")
        flags = smoke.research_compile_flags(kernel)
        leaf = str(kernel / Path(smoke.CAMISP_POWER_OBJECTS[0]).parent)
        self.assertIn("-I" + leaf, flags.split())
        self.assertIn("-I" + str(kernel / smoke.CAMISP_RESOURCE_PLAN["include_directory"]),
                      flags.split())
        self.assertTrue(flags.startswith("KCFLAGS="))
        source = Path(__file__).with_name("kernel-object-smoke.py").read_text()
        self.assertIn("make.append(research_compile_flags(kernel))", source)

    def test_shared_supplier_plan_records_checks_and_both_variants(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.check_output([
            sys.executable, str(root / "ci/kernel-object-smoke.py"),
            "--research-owners", "--plan-only"], cwd=root, text=True)
        plan = json.loads(result)
        shared = plan["camisp_shared_supplier"]
        self.assertEqual(shared["scope"], "object-only; shared composite/vmlinux link untested")
        self.assertEqual(shared["config_variants"], [{"KUNIT": "y"}, {"KUNIT": "n"}])
        self.assertEqual(shared["payload_sha256"], smoke.CAMISP_SHARED_PLAN["source_sha256"])
        self.assertEqual(shared["source_check"]["status"], "passed")
        self.assertEqual(shared["excluded_from_staging"], ["Kbuild.shared"])
        self.assertEqual(shared["objects"], list(smoke.CAMISP_POWER_OBJECTS + smoke.CAMISP_SHARED_OBJECTS))
        for name in shared["objects"]:
            self.assertEqual(plan["objects"].count(name), 1)
        for name, digest in shared["payload_sha256"].items():
            self.assertEqual(plan["research_source_sha256"][name], digest)

    def test_shared_supplier_variants_require_native_dependencies(self):
        command = smoke.config_options(Path("kernel"), Path("objects"), True)
        enabled = [command[i + 1] for i, value in enumerate(command) if value == "-e"]
        for symbol in (*smoke.CAMISP_SHARED_PLAN["required_enabled"], "KUNIT"):
            self.assertIn(symbol, enabled)
        source = Path(__file__).with_name("kernel-object-smoke.py").read_text()
        self.assertIn("variant_objects += CAMISP_SHARED_OBJECTS", source)
        for tag in ("kunit_enabled_objects", "kunit_disabled_objects"):
            self.assertIn('manifest["camisp_shared_supplier"]["' + tag + '"]', source)
        self.assertIn("(*CAMISP_ENABLE, *CAMISP_RESOURCE_ENABLE, *CAMISP_POWER_ENABLE)", source)

    def test_shared_supplier_payload_hash_drift_stops_plan(self):
        altered = dict(smoke.CAMISP_SHARED_PLAN)
        altered["source_sha256"] = dict(altered["source_sha256"])
        source = next(iter(smoke.CAMISP_SHARED_SOURCES))
        altered["source_sha256"][source] = "0" * 64
        with patch.object(smoke, "CAMISP_SHARED_PLAN", altered), \
                patch.object(sys, "argv", ["kernel-object-smoke.py", "--research-owners", "--plan-only"]), \
                patch.object(smoke.subprocess, "check_output", return_value="source checks passed"), \
                self.assertRaisesRegex(ValueError, "shared VMM payload hash mismatch"):
            smoke.main()

    def test_camisp_resources_manifest_rejects_shipping_provider_destination(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / smoke.CAMISP_RESOURCE_MANIFEST).read_text())
        data["sources"][next(iter(data["sources"]))] = "drivers/clk/mediatek/clk-mt6878-cam.c"
        with patch.object(smoke.json, "loads", return_value=data):
            with self.assertRaisesRegex(ValueError, "closure"):
                smoke.camisp_resource_staging(root)

    def test_gpu_power_staging_matches_reviewed_manifests(self):
        root = Path(__file__).resolve().parents[1]
        for bundle in ("mfg0-supplier-draft", "bound-parent-draft"):
            manifest = json.loads((root / "patches/gpu" / bundle / "STAGING.json").read_text())
            for source, destination in manifest["sources"].items():
                self.assertEqual(smoke.RESEARCH_SOURCES[source], destination)
            for name in manifest["objects"]:
                self.assertIn(name, smoke.RESEARCH_OBJECTS)
                self.assertNotIn(name, smoke.OBJECTS)

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
        video = (destination / "mt6878-native-video.c").read_text()
        self.assertIn("mt6878_camera_cold_frame(&v->joint_reset", video)
        self.assertIn("mt6878_camera_cold_probe(&v->capture", video)
        self.assertNotIn("mt6878_native_capture_frame(&v->capture", video)

    def test_failed_overlay_does_not_publish_partial_graph(self):
        root, graph, _ = self.camera_overlay_fixture()
        original = graph.read_text().replace('#include "mt6878-seninf-contract.h"', '#include "stale-contract.h"')
        graph.write_text(original)
        with self.assertRaises(smoke.subprocess.CalledProcessError):
            smoke.stage_camera_overlays(self.package, root)
        self.assertEqual(graph.read_text(), original)
        destination = self.package / Path(next(iter(smoke.CAMERA_SOURCES.values()))).parent
        self.assertFalse((destination / graph.name).exists())

    def test_repeat_worker_follows_cold_overlay_and_keeps_graph(self):
        root, graph, _ = self.camera_overlay_fixture()
        smoke.stage_camera_overlays(self.package, root)
        before = graph.read_bytes()
        smoke.stage_camera_repeat(self.package, root)
        self.assertEqual(graph.read_bytes(), before)
        destination = self.package / Path(next(iter(smoke.CAMERA_SOURCES.values()))).parent
        video = (destination / "mt6878-native-video.c").read_text()
        self.assertIn("mt6878_capture_epoch_submit(v->epoch", video)
        self.assertIn("mt6878_camera_cold_probe(&v->capture", video)
        self.assertLess(video.index("cancel_work_sync(&v->frame_work)"),
                        video.index("mt6878_capture_epoch_free(v->epoch)"))
        for name in smoke.CAMERA_REPEAT_OBJECTS:
            self.assertIn(name, smoke.RESEARCH_OBJECTS)
            self.assertNotIn(name, smoke.OBJECTS)

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


class GnssModuleGate(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.kernel = self.root / "kernel"
        self.kernel.mkdir()
        self.report = self.root / "report"
        self.report.mkdir()

    def test_plan_has_exact_stack_real_suppliers_and_no_activation(self):
        with patch.object(smoke.urllib.request, "urlopen") as network, \
                patch.object(smoke.subprocess, "run") as commands:
            plan = smoke.gnss_module_plan()
        network.assert_not_called()
        commands.assert_not_called()
        self.assertEqual([name[:4] for name in plan["prerequisites"]],
                         [str(n) for n in range(1001, 1009)])
        self.assertEqual(plan["suppliers"], ["kernel vmlinux/modules", "connadp", "conninfra"])
        self.assertEqual(plan["variants"], ["baseline-1001-1008", "candidate-1009"])
        self.assertEqual(plan["status"], "pending")
        for name in ("shipping_activation", "hardware_tested", "phone_abi_compatible"):
            self.assertFalse(plan[name])

    def test_missing_or_mutable_archive_identity_fails(self):
        package = self.root / "package"
        package.mkdir()
        original = (smoke.PACKAGE / "APKBUILD").read_text()
        identity = smoke.gnss_archive_identity(True)
        for source in (original.replace(identity["commit"], "main"),
                       original.replace(identity["sha512"], "0" * 128) +
                       "\n" + "0" * 128 + "  " + identity["archive"] + "\n",
                       original.replace("https://github.com/NothingOSS/", "https://example.invalid/")):
            (package / "APKBUILD").write_text(source)
            with patch.object(smoke, "PACKAGE", package), self.assertRaises(ValueError):
                smoke.gnss_archive_identity(True)

    def test_local_full_module_execution_rejected_before_writes(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                patch.object(smoke.subprocess, "run") as commands, \
                self.assertRaisesRegex(ValueError, "CI-only"):
            smoke.compile_gnss_tx_module(self.kernel, self.root, self.report)
        commands.assert_not_called()
        self.assertEqual(list(self.report.iterdir()), [])

    def test_connectivity_flags_match_packaged_values(self):
        source = (smoke.PACKAGE / "APKBUILD").read_text()
        helper = source.split("_connectivity_make() {", 1)[1].split("\n}", 1)[0]
        flags = smoke.gnss_connectivity_make([], self.kernel, self.root, self.root, self.root, self.root)
        for arg in flags:
            key = arg.split("=", 1)[0]
            self.assertIn(key + "=", helper)
            if key not in ("M", "KERNEL_SRC", "KERNEL_OUT", "KO_CODE_PATH", "DEVICE_MODULES_PATH", "TOP", "KCFLAGS"):
                self.assertIn(arg, helper)

    def test_adapter_fuzz_cannot_hide_extra_source_changes(self):
        device = self.root / "adapter-source"
        targets = {
            "drivers/misc/mediatek/connectivity/common/wmt_build_in_adapter.c": "CONN_DBG_DEVICE_NAME",
            "drivers/misc/mediatek/connectivity/power_throttling/adapter.c": "CONN_PWR_DEVICE_NAME",
        }
        before = {}
        for name, argument in targets.items():
            path = device / name
            path.parent.mkdir(parents=True, exist_ok=True)
            before[name] = "class_create(THIS_MODULE, " + argument + ");\n/* unchanged */\n"
            path.write_text(before[name])

        def apply(command):
            self.assertIn("--fuzz=2", command)
            for name, argument in targets.items():
                (device / name).write_text(before[name].replace("THIS_MODULE, ", "", 1))

        with patch.object(smoke, "run", side_effect=apply):
            identities = smoke.prepare_gnss_adapter(device)
        self.assertEqual(set(identities), set(targets))
        for name in targets:
            self.assertNotEqual(identities[name]["before_sha256"], identities[name]["after_sha256"])
            (device / name).write_text(before[name])

        def tamper(command):
            apply(command)
            path = device / next(iter(targets))
            path.write_text(path.read_text() + "unexpected change\n")

        with patch.object(smoke, "run", side_effect=tamper), self.assertRaisesRegex(ValueError, "changed more"):
            smoke.prepare_gnss_adapter(device)

    def test_imports_must_match_real_export_tables(self):
        module = self.root / "gps.ko"
        module.write_bytes(b"test fixture only")
        tables = [self.root / "kernel.symvers", self.root / "conninfra.symvers"]
        tables[0].write_text("0x00000000 printk vmlinux EXPORT_SYMBOL\n")
        tables[1].write_text("0x00000000 conninfra_pwr_on conninfra EXPORT_SYMBOL_GPL\n")
        with patch.object(smoke, "object_identity", return_value={"format": "ELF", "machine": "AArch64"}), \
                patch.object(smoke.subprocess, "check_output", return_value=" U printk\n U conninfra_pwr_on\n w optional\n"):
            result = smoke.gnss_module_evidence(module, tables)
            self.assertEqual(set(result["imports"]), {"printk", "conninfra_pwr_on"})
            self.assertEqual(result["weak_imports"], ["optional"])
            self.assertEqual(result["imports"]["conninfra_pwr_on"]["table"], str(tables[1]))
            tables[1].write_text("0x00000000 unrelated conninfra EXPORT_SYMBOL\n")
            with self.assertRaisesRegex(ValueError, "conninfra_pwr_on"):
                smoke.gnss_module_evidence(module, tables)
            tables[1].write_text("")
            with self.assertRaisesRegex(ValueError, "missing built"):
                smoke.gnss_module_evidence(module, tables)
            tables[1].write_text(tables[0].read_text())
            with self.assertRaisesRegex(ValueError, "duplicate"):
                smoke.gnss_module_evidence(module, tables)
            tables[1].write_text("untracked export fixture\n")
            with self.assertRaisesRegex(ValueError, "invalid built"):
                smoke.gnss_module_evidence(module, tables)

    def mocked_build(self, fail_phase=None, missing_exports=None):
        # All compiler/ELF calls are mocked; these fixtures only test CI ordering.
        vendor = self.root / "vendor"
        gps = vendor / "connectivity/gps/data_link/plat/v051"
        gps.mkdir(parents=True)
        (gps / "Kbuild").write_text("# Kbuild fixture\n")
        original = vendor / "baseline.c"
        original.write_text("baseline\n")
        staged = {"stacked_source_sha512": {"baseline.c": hashlib.sha512(original.read_bytes()).hexdigest()}}
        device = self.root / "device"
        adapter = device / "drivers/misc/mediatek/connectivity"
        adapter.mkdir(parents=True)
        conninfra = vendor / "connectivity/conninfra"
        conninfra.mkdir()
        calls = []

        def command(argv, **kwargs):
            argv = list(map(str, argv))
            if argv[0] != "make":
                raise AssertionError("unexpected real command: " + repr(argv))
            output = Path(next(arg[2:] for arg in argv if arg.startswith("O=")))
            module_arg = next((arg[2:] for arg in argv if arg.startswith("M=")), None)
            if argv[-1] == "olddefconfig":
                phase = "kernel-config"
            elif module_arg is None:
                phase = "kernel-exports"
                (output / "vmlinux").write_bytes(b"mocked kernel")
                if missing_exports != "kernel":
                    (output / "Module.symvers").write_text("mocked exports\n")
            elif Path(module_arg) == adapter:
                phase = "connadp"
            elif Path(module_arg) == conninfra:
                phase = "conninfra"
            elif argv[-1] == "clean":
                phase = "gnss-clean"
            else:
                phase = "baseline-1001-1008" if original.read_text() == "baseline\n" else "candidate-1009"
            calls.append((phase, argv))
            if fail_phase == phase:
                kwargs["stdout"].write("first supplier failure\n")
                raise subprocess.CalledProcessError(2, argv)
            if phase in ("connadp", "conninfra") and missing_exports != phase:
                (Path(module_arg) / "Module.symvers").write_text("mocked exports\n")

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                patch.object(smoke, "prepare_gnss_tx_sources", return_value=(SimpleNamespace(), vendor, staged, {})), \
                patch.object(smoke, "fetch_gnss_archive", return_value=device), \
                patch.object(smoke, "prepare_gnss_adapter", return_value={}), \
                patch.object(smoke, "run"), \
                patch.object(smoke, "apply_gnss_tx", side_effect=lambda *_: original.write_text("candidate\n")) as apply, \
                patch.object(smoke.subprocess, "check_output", return_value="clang version 21.1.0\n"), \
                patch.object(smoke.subprocess, "run", side_effect=command), \
                patch.object(smoke, "object_identity", return_value={"format": "ELF", "machine": "AArch64"}), \
                patch.object(smoke, "gnss_module_evidence", side_effect=lambda *_: {"format": "ELF"}):
            if fail_phase or missing_exports:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    smoke.compile_gnss_tx_module(self.kernel, self.root, self.report)
            else:
                smoke.compile_gnss_tx_module(self.kernel, self.root, self.report)
            applied = apply.call_count
        manifest = json.loads((self.report / "gnss-tx-module/MODULE-MANIFEST.json").read_text())
        return calls, manifest, applied

    def test_full_module_order_strict_modpost_and_separate_candidate(self):
        calls, manifest, applied = self.mocked_build()
        self.assertEqual([phase for phase, _ in calls], ["kernel-config", "kernel-exports", "connadp", "conninfra",
                                                       "baseline-1001-1008", "gnss-clean", "candidate-1009"])
        self.assertEqual(applied, 1)
        self.assertEqual(manifest["status"], "passed")
        self.assertNotEqual(manifest["baseline-1001-1008"]["source_sha512"],
                            manifest["candidate-1009"]["source_sha512"])
        self.assertEqual(set(manifest["supplier_symvers_sha256"]), {"kernel.symvers", "connadp.symvers", "conninfra.symvers"})
        for phase, argv in calls:
            self.assertIn("KBUILD_MODPOST_WARN=", argv)
            self.assertIn("KBUILD_MODPOST_NOFINAL=", argv)
            if phase == "kernel-exports":
                self.assertEqual(argv[-2:], ["vmlinux", "modules"])
            if phase == "connadp":
                self.assertIn("CONFIG_MTK_COMBO=m", argv)
                self.assertNotIn("CONFIG_MTK_COMBO=y", argv)
            if phase in ("baseline-1001-1008", "candidate-1009"):
                tables = [arg for arg in argv if arg.startswith("KBUILD_EXTRA_SYMBOLS=")][-1]
                self.assertIn("connectivity/Module.symvers", tables)
                self.assertIn("conninfra/Module.symvers", tables)
        self.assertEqual(list(self.report.rglob("*.ko")), [])

    def test_baseline_failure_preserved_without_applying_candidate(self):
        calls, manifest, applied = self.mocked_build(fail_phase="baseline-1001-1008")
        self.assertEqual(applied, 0)
        self.assertEqual(calls[-1][0], "baseline-1001-1008")
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["phase"], "baseline-1001-1008")
        self.assertEqual((self.report / "gnss-tx-module/baseline-1001-1008.log").read_text(), "first supplier failure\n")
        self.assertNotIn("candidate-1009", manifest)

    def test_supplier_failure_stops_before_gnss(self):
        calls, manifest, applied = self.mocked_build(fail_phase="conninfra")
        self.assertEqual(applied, 0)
        self.assertEqual(calls[-1][0], "conninfra")
        self.assertEqual(manifest["phase"], "conninfra")
        self.assertEqual(manifest["status"], "failed")
        self.assertNotIn("baseline-1001-1008", manifest)

    def test_missing_kernel_exports_cannot_reach_supplier_modpost(self):
        calls, manifest, applied = self.mocked_build(missing_exports="kernel")
        self.assertEqual(applied, 0)
        self.assertEqual(calls[-1][0], "kernel-exports")
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("missing built GNSS supplier exports", manifest["error"])

    def test_missing_adapter_exports_cannot_reach_conninfra_modpost(self):
        calls, manifest, applied = self.mocked_build(missing_exports="connadp")
        self.assertEqual(applied, 0)
        self.assertEqual(calls[-1][0], "connadp")
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("missing built GNSS supplier exports", manifest["error"])

    def test_candidate_failure_retains_successful_baseline(self):
        calls, manifest, applied = self.mocked_build(fail_phase="candidate-1009")
        self.assertEqual(applied, 1)
        self.assertEqual(calls[-1][0], "candidate-1009")
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("baseline-1001-1008", manifest)
        self.assertNotIn("candidate-1009", manifest)

    def test_opt_in_plan_and_workflow_do_not_dispatch_or_ship(self):
        root = Path(smoke.__file__).resolve().parents[1]
        result = subprocess.check_output([sys.executable, str(root / "ci/kernel-object-smoke.py"),
                                          "--gnss-tx-module", "--plan-only"], cwd=root, text=True)
        plan = json.loads(result)
        self.assertEqual(plan["objects"], [])
        self.assertEqual(plan["dtbs"], [])
        self.assertEqual(plan["gnss_nonblocking_tx_module"]["status"], "pending")
        workflow = (root / ".github/workflows/gnss-tx-module.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        for forbidden in ("pull_request:", "push:", "schedule:", "modules_install", "insmod", "modprobe"):
            self.assertNotIn(forbidden, workflow)
        self.assertIn("--gnss-tx-module", workflow)
        self.assertIn("if: always()", workflow)


class NativeProviderOrdering(unittest.TestCase):
    def test_modem_registration_policy_gets_real_kunit_variants(self):
        source = inspect.getsource(smoke.compile_md_pmic)
        self.assertIn('rails.inputs()', source)
        self.assertIn('rails.registration_header(before)', source)
        self.assertIn('registration_source_sha256', source)
        self.assertIn('registration_variants', source)
        self.assertIn('("y", "n")', source)
        self.assertIn('"registration-kunit-" + unit', source)
        self.assertIn('finally:\n        header.write_text(before)', source)

    def test_exact_prepared_source_is_checked_before_native_objects(self):
        source = Path(smoke.__file__).read_text()
        checked = source.index('"--prepared-kernel", kernel])')
        objects = source.index('output = args.work / "objects"')
        self.assertLess(checked, objects)
        self.assertIn('source_report = report / "native-provider-inputs"', source[:checked])
        self.assertIn('shutil.copyfile(kernel / name, target)', source[:checked])


class FlatMetadataCompile(unittest.TestCase):
    def test_candidate_compile_restores_packaged_source_on_success_and_failure(self):
        canonical = Path("patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c").read_text()
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                kernel, output, report = (root / name for name in ("kernel", "output", "report"))
                source = kernel / "drivers/misc/gpueb-flat-analysis.c"
                source.parent.mkdir(parents=True)
                source.write_text(canonical)
                artifact = output / "drivers/misc/gpueb-flat-analysis.o"
                artifact.parent.mkdir(parents=True)
                artifact.write_bytes(b"object fixture; never executed")
                (output / ".config").write_text("CONFIG_TETRIS_GPUEB_FLAT_ANALYSIS=m\n")
                report.mkdir()

                def command(argv):
                    self.assertIn("tetris_gpueb_flat_metadata_read", source.read_text())
                    self.assertEqual(argv[-1], "drivers/misc/gpueb-flat-analysis.o")
                    if fail:
                        raise RuntimeError("compiler failure fixture")

                with patch.object(smoke, "run", side_effect=command), \
                        patch.object(smoke, "object_identity", return_value={"machine": "AArch64"}):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "compiler failure"):
                            smoke.compile_flat_metadata(["make"], kernel, output, report)
                    else:
                        result = smoke.compile_flat_metadata(["make"], kernel, output, report)
                        self.assertFalse(result["hardware_tested"])
                        self.assertFalse(result["shipping_source_changed"])
                        self.assertEqual(result["source_sha256"],
                                         "e0ac3e88c4a23faabf0cc80f406a52e7eda1ac44af0f9004df65de730a367204")
                self.assertEqual(source.read_text(), canonical)


if __name__ == "__main__":
    unittest.main()
