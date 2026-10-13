#!/usr/bin/env python3
"""Source, package planning and real patch tests only. No C build or target code."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import stage
import prepare


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = stage.ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878"
        cls.pristine = stage.ROOT.parent / ("linux-" + stage.helpers()[0].LINUX)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.bundle = stage.sources(cls.vendor, cls.pristine)
        cls.link, cls.abi, cls.real, cls.kernel, cls.overlays, cls.after = cls.bundle

    def test_actual_runtime_and_resource_callers(self):
        main = self.after[stage.UTIL + "ccci_util_lib_main.c"]
        for symbol in ("ccci_tetris_log_init", "ccci_tetris_events_init", "ccci_tetris_pin_init", "ccci_common_sysfs_init"):
            self.assertIn("ret = " + symbol + "();", main)
            self.assertLess(main.index("ret = " + symbol + "();"), main.index("ret = mtk_ccci_owned_smem_init();"))
        resource = self.after[stage.PLATFORM]
        self.assertIn("ret = ccci_tetris_consumer_resources(dev_ptr, hw_info);", resource)
        native = resource.split("ret = ccci_tetris_consumer_resources", 1)[1].split("#else", 1)[0]
        self.assertNotIn("ioremap_wc", native)
        self.assertIn("return ret;", native)
        sysfs = self.after[stage.UTIL + "ccci_util_lib_sys.c"]
        allowed = sysfs.split("static struct attribute *ccci_default_attrs[] = {", 1)[1].split("#else", 1)[0]
        self.assertNotIn("ccci_attr_boot.attr", allowed)
        self.assertNotIn("ccci_attr_pincfg.attr", allowed)

    def test_real_allocations_and_failure_cleanup_no_readiness_cookie(self):
        for file in ("util-log.h", "util-events.h", "util-pin.h"):
            text = (stage.HERE / file).read_text()
            self.assertIn("kzalloc", text)
            self.assertIn("-ENOMEM", text)
            self.assertNotIn("static bool", text)
            self.assertNotIn("ready", text)
        log = (stage.HERE / "util-log.h").read_text()
        self.assertIn("node_array[i].init_size", log)
        self.assertIn("vfree(ccci_event_buffer.buffer)", log)
        self.assertNotIn("proc_create", log)
        resource = (stage.HERE / "consumer-resources.h").read_text()
        for operation in ("platform_get_irq", "devm_ioremap_resource", "mt6878_md_native_on_validate", "PTR_ERR"):
            self.assertIn(operation, resource)

    def test_actual_complete_package_patch_order_against_shipping_vendor(self):
        with tempfile.TemporaryDirectory(prefix="native-image-prepare-test-") as directory:
            root = Path(directory).resolve()
            source = root / "shipping"
            source.mkdir()
            archive = root / "vendor.tar"
            subprocess.run(["git", "-C", self.vendor, "archive", "--format=tar", self.link.VENDOR, "-o", archive], check=True)
            with tarfile.open(archive) as handle:
                handle.extractall(source, filter="data")
            manifest, _, package = self.link.helpers()[2].load("image_test_objects",
                stage.ROOT / "patches/modem/drafts/runtime-object-ci/check_objects.py").plan()
            for name in manifest["vendor_prepare"]:
                subprocess.run(["patch", "--batch", "-p1", "-d", source, "-i", package / name],
                               check=True, stdout=subprocess.DEVNULL)
            paths = []
            for name, data in self.overlays.items():
                path = root / name
                path.write_bytes(data)
                paths.append(path)
            # Source-only stale products must not be adopted, even from a valid tree.
            (source / "stale.o").write_bytes(b"not build evidence")
            prepare.prepare(source, root / "native", paths)
            self.assertFalse((root / "native/stale.o").exists())
            for name, value in self.after.items():
                self.assertEqual((root / "native" / name).read_text(), value)

    def populate(self, tree):
        for name in (stage.KERNEL, stage.DEVICE):
            shutil.copytree(stage.ROOT / "pmaports" / name, tree / name)

    def test_full_fresh_package_plan_security_checksums_and_f25(self):
        with tempfile.TemporaryDirectory(prefix="native-image-package-test-") as directory:
            tree = Path(directory).resolve() / "copy"
            self.populate(tree)
            original = {str(path.relative_to(tree)): path.read_bytes() for path in tree.rglob("*") if path.is_file()}
            # Only pure frozen package composition is admitted here. No compiler
            # or hardware command is called; this is not an actual CI PASS.
            with patch.dict(os.environ, {"CI": "true", "GITHUB_ACTIONS": "true"}), \
                 patch.object(stage, "sources", return_value=self.bundle):
                inputs, outputs, report = stage.plan(tree, self.vendor, self.pristine, 190)
            self.assertEqual(original, {str(path.relative_to(tree)): path.read_bytes() for path in tree.rglob("*") if path.is_file()})
            apk = outputs[stage.KERNEL + "/APKBUILD"].decode()
            cfg = outputs[stage.KERNEL + "/" + stage.CONFIG].decode()
            self.assertIn("py3-elftools", apk)
            self.assertNotIn("py3-pyelftools", apk)
            self.assertIn("\t_build_native_start\n", apk)
            self.assertIn('build() {\n\t. "$srcdir/native-image.sh"', apk)
            self.assertNotIn("\t_build_modem_link\n", apk)
            self.assertNotIn("\t_build_ccci_metadata_only\n", apk)
            self.abi.security_profile(self.abi.config(inputs[stage.KERNEL + "/" + stage.CONFIG].decode()), self.abi.config(cfg))
            self.assertEqual(report["required_uboot_commit"], "f25c01444a642c6fca857bd9678ef438ec371988")
            self.assertIn("untouched", report["stock_slot"])
            for name, value in self.abi.config(cfg).items():
                if name in self.real.DISABLED:
                    self.assertEqual(value, "n")
            for name, data in outputs.items():
                if not name.startswith(stage.KERNEL + "/") or name.endswith("APKBUILD"):
                    continue
                self.assertIn(stage.sha(data, "sha512") + "  " + Path(name).name + "\n", apk)
            script = outputs[stage.KERNEL + "/native-image.sh"]
            self.assertNotIn(b"@PATCHES@", script)
            subprocess.run(["sh", "-n"], input=script, check=True)
            subprocess.run(["sh", "-n"], input=apk.encode(), check=True)
            block = outputs[stage.KERNEL + "/native-image-modprobe.conf"].decode()
            self.assertEqual(block.count(" /bin/false"), 9)
            self.assertIn(stage.BOARD.encode(), outputs[stage.DEVICE + "/deviceinfo"])

    def test_local_stage_guard_precedes_mutation(self):
        with tempfile.TemporaryDirectory(prefix="native-image-guard-") as directory:
            root = Path(directory).resolve()
            with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}), \
                 patch.object(stage, "plan") as plan:
                with self.assertRaisesRegex(ValueError, "CI-only"):
                    stage.stage(root, self.vendor, self.pristine, root / "report.json", 190, True)
                plan.assert_not_called()
            self.assertFalse((root / "report.json").exists())

    def test_kernel_layers_native_default_off_and_disabled_real_resources(self):
        names = list(self.kernel)
        self.assertEqual(names, ["0185-native-modem-rails.patch", "0186-native-modem-rails-registration-dt.patch",
            "0188-native-modem-real-on.patch", "0189-native-modem-start-api.patch", "0190-native-modem-start-board.patch"])
        dt = self.kernel[names[-1]].decode()
        self.assertIn("power-domains = <&md_spm 0>", dt)
        self.assertIn("GIC_SPI 491", dt)
        self.assertIn("0x0d180000", dt)
        self.assertNotIn('status = "okay"', dt)
        self.assertIn("default n", self.kernel[names[-2]].decode())

    def test_no_unreviewed_activation_or_security_weakening(self):
        script = (stage.HERE / "native-image.sh").read_text()
        for bad in ("KBUILD_MODPOST_WARN=1", "KBUILD_MODPOST_NOFINAL=1", "CFI=0", "insmod", "rmmod", "fastboot", "SKIP"):
            if bad == "SKIP":
                self.assertNotIn("=SKIP", script)
            else:
                self.assertNotIn(bad, script)
        self.assertIn("_devmods_dir/drivers", script.replace('"$_devmods_dir"/drivers', '$_devmods_dir/drivers'))
        self.assertIn("_package_native_start", script)

    def test_manifest_closure(self):
        stage.verify_manifest()


class DTParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules["native_image_dt"] = stage.load("native_image_dt", stage.ROOT / "patches/modem/check_preflight_dt.py")
        cls.check = stage.load("image_dt_test", stage.HERE / "check_dt.py")

    def trees(self):
        # Synthetic scalar parser cases only, never a compiled DT/loader proof.
        def cells(*values):
            return b"".join(value.to_bytes(4, "big") for value in values)
        baseline = {"/modem": {"status": b"disabled\0", "md-vmodem-supply": cells(3),
            "md-vsram-supply": cells(4), "md-vdigrf-supply": cells(5)},
            self.check.SPM: {"phandle": cells(1), "#power-domain-cells": cells(1)},
            "/soc@0/syscon@10001000": {"phandle": cells(2)},
            "/rail/1": {"phandle": cells(3), "status": b"disabled\0"},
            "/rail/2": {"phandle": cells(4), "status": b"disabled\0"},
            "/rail/3": {"phandle": cells(5), "status": b"disabled\0"},
            "/scp": {"status": b"okay\0", "test-scalar": b"unchanged"}}
        baseline.update({path: {"status": b"okay\0"} for path in self.check.HIF})
        candidate = {name: dict(props) for name, props in baseline.items()}
        candidate["/modem"].update({"reg": cells(0, 0x0d180000, 0, 0x2000, 0, 0x1c803000, 0, 0x1000),
            "interrupts": cells(0, 491, 4, 0, 0, 228, 4, 0, 0, 229, 4, 0), "power-domains": cells(1, 0),
            "ccci-infracfg": cells(2), "mediatek,mdhif-type": cells(6), "mediatek,cldma-capability": cells(14),
            "mediatek,offset-epon-md1": cells(0x64, 6), "mediatek,boot-status-config": cells(1)})
        for path in self.check.HIF:
            candidate[path]["status"] = b"disabled\0"
        return baseline, candidate

    def test_exact_resource_delta_no_activation(self):
        self.assertEqual(self.check.validate(*self.trees())["consumer"], "disabled")

    def test_scp_changes_are_not_hidden(self):
        before, after = self.trees()
        after["/scp"]["test-scalar"] = b"changed"
        with self.assertRaisesRegex(ValueError, "unexpected compiled native DT delta"):
            self.check.validate(before, after)

    def test_enablement_requires_new_real_admission_not_fixture_status_flip(self):
        for node in ("/modem", "/rail/1", self.check.HIF[0]):
            before, after = self.trees()
            after[node]["status"] = b"okay\0"
            with self.subTest(node=node), self.assertRaises(ValueError):
                self.check.validate(before, after)


if __name__ == "__main__":
    unittest.main()
