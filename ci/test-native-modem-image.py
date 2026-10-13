#!/usr/bin/env python3
"""Static staging and negative DT tests; no compiler or hardware execution."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


stage = module("native_stage", "ci/stage-native-modem-image.py")
check = module("native_dt", "ci/check-native-modem-image-dt.py")
loader = module("native_loader", "ci/select-native-modem-uboot.py")
sys.modules["check"] = check.hif
hif_test = module("hif_tests", "patches/modem/drafts/runtime-hif-dt/test_dt.py")


class ImageTests(unittest.TestCase):
    def test_local_staging_refused_before_any_write(self):
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}), \
                patch.object(stage, "frozen") as frozen:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                stage.stage(ROOT / "pmaports", Path("unused"))
            frozen.assert_not_called()

    def test_never_modify_shipping_checkout(self):
        with patch.dict("os.environ", {"CI": "true", "GITHUB_ACTIONS": "true"}):
            with self.assertRaisesRegex(ValueError, "shipping checkout"):
                stage.stage(ROOT / "pmaports", Path("unused"))

    def test_separate_matched_package_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for relative in (stage.KERNEL, stage.DEVICE):
                shutil.copytree(ROOT / "pmaports" / relative, tree / relative)
            with patch.dict("os.environ", {"CI": "true", "GITHUB_ACTIONS": "true"}):
                result = stage.stage(tree, tree / "result.json")
                with self.assertRaisesRegex(ValueError, "already staged"):
                    stage.stage(tree, tree / "again.json")
            apk = (tree / stage.KERNEL / "APKBUILD").read_text()
            self.assertIn("pkgrel=184\n", apk)
            self.assertIn('die "native MD diagnostic exclusion unresolved: $_symbol"', apk)
            self.assertLess(apk.index("0180-native-md"), apk.index("0181-native-camera"))
            self.assertIn('mediatek/' + stage.BOARD + '.dtb \\\n', apk)
            self.assertIn('"$pkgdir/boot/dtbs/mediatek/' + stage.BOARD + '.dtb"', apk)
            header_fix = (tree / stage.KERNEL / "0183-native-camera-header-parent.patch").read_text()
            self.assertIn('+#include "../mtk-pm-domains.h"', header_fix)
            self.assertEqual(header_fix.count("diff --git"), 1)
            self.assertIn("0184-native-modem-single-ack.patch", apk)
            self.assertEqual(result["kernel_package"], "7.2.1-r184")
            self.assertEqual(result["source_commit"], stage.SOURCE)
            self.assertFalse(result["modem_consumer_enabled"])
            config = (tree / stage.KERNEL / "config-postmarketos-mediatek-mt6878.aarch64").read_text()
            for name in stage.DISABLED:
                self.assertIn("# CONFIG_" + name + " is not set\n", config)
            for name in stage.ENABLED:
                self.assertIn("CONFIG_" + name + "=y\n", config)
            self.assertIn(stage.BOARD, (tree / stage.DEVICE / "deviceinfo").read_text())
            fit = (tree / stage.DEVICE / "boot_image.its").read_text()
            self.assertIn('data = /incbin/("' + stage.BOARD + '.dtb");', fit)
            self.assertNotIn('"mt6878-nothing-tetris-native.dtb"', fit)
            self.assertEqual(fit.count('/incbin/('), 3)
            self.assertEqual(result["fit_dtb"], stage.BOARD + ".dtb")
            self.assertIn('"mt6878-nothing-tetris-native.dtb"',
                          (ROOT / "pmaports" / stage.DEVICE / "boot_image.its").read_text())

    def test_fit_template_drift_is_not_silently_staged(self):
        for change in ("missing", "duplicate"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                for relative in (stage.KERNEL, stage.DEVICE):
                    shutil.copytree(ROOT / "pmaports" / relative, tree / relative)
                fit = tree / stage.DEVICE / "boot_image.its"
                original = fit.read_text()
                fit.write_text(original.replace("mt6878-nothing-tetris-native.dtb", "unreviewed.dtb")
                               if change == "missing" else original + original)
                with patch.dict("os.environ", {"CI": "true", "GITHUB_ACTIONS": "true"}):
                    with self.assertRaises(ValueError):
                        stage.stage(tree, tree / "result.json")

    def test_board_patch_applies_without_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            makefile = tree / "arch/arm64/boot/dts/mediatek/Makefile"
            makefile.parent.mkdir(parents=True)
            makefile.write_text("# SPDX-License-Identifier: GPL-2.0\ndtb-$(CONFIG_ARCH_MEDIATEK) += mt2712-evb.dtb\n")
            binding = tree / "Documentation/devicetree/bindings/power/mediatek,power-controller.yaml"
            binding.parent.mkdir(parents=True)
            binding.write_text("  $nodename:\n    pattern: '^power-controller(@[0-9a-f]+)?$'\n\n")
            subprocess.run(["git", "apply", "--verbose", "-"], input=stage.dt_patch(),
                           cwd=tree, text=True, check=True, capture_output=True)
            self.assertTrue((makefile.parent / (stage.BOARD + ".dts")).is_file())
            self.assertIn("power-controller(-modem)?", binding.read_text())

    def fixture(self):
        normal, dt = hif_test.fixture()
        normal[check.SPM] = {"compatible": b"mediatek,mt6878-scpsys\0syscon\0"}
        dt[check.SPM] = dict(normal[check.SPM])
        ints = hif_test.ints
        dt[check.NEMI] = {"compatible": b"mediatek,mt6878-nemicfg_ao_mem_reg_bus\0syscon\0",
                          "reg": ints([0x10270000, 0x1000]), "status": b"disabled\0", "phandle": ints([77])}
        dt[check.SUPPLIER] = {"compatible": b"mediatek,mt6878-modem-power-controller\0",
                              "#address-cells": ints([1]), "#size-cells": ints([0]),
                              "#power-domain-cells": ints([1]), "access-controllers": ints([42, 77]),
                              "status": b"disabled\0"}
        dt[check.DOMAIN] = {"reg": ints([0]), "#power-domain-cells": ints([0]), "status": b"disabled\0"}
        for marker in check.MARKERS:
            dt["/chosen"][marker] = b""
        return normal, dt

    def test_native_header_fix_applies_exactly_without_research_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            header = tree / "drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.h"
            header.parent.mkdir(parents=True)
            before = stage.frozen("patches/camera-camisp/power/mt6878-cam-power.h").decode()
            header.write_text(before)
            subprocess.run(["git", "apply", "--verbose", "--whitespace=error", "-"],
                           input=stage.native_header_patch(), cwd=tree, text=True, check=True, capture_output=True)
            self.assertEqual(header.read_text(), before.replace('#include "mtk-pm-domains.h"',
                                                               '#include "../mtk-pm-domains.h"'))

    def test_modem_ack_fix_applies_only_to_modem_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            header = tree / "drivers/pmdomain/mediatek/mt6878-modem-pm.h"
            header.parent.mkdir(parents=True)
            packaged = stage.frozen("pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0113-pmdomain-mediatek-mt6878-modem-power.patch").decode()
            before = packaged.split("@@ -0,0 +1,162 @@\n", 1)[1]
            before = "".join(line[1:] + "\n" for line in before.splitlines() if line.startswith("+"))
            header.write_text(before)
            subprocess.run(["git", "apply", "--verbose", "--whitespace=error", "-"],
                           input=stage.modem_ack_patch(), cwd=tree, text=True, check=True, capture_output=True)
            self.assertEqual(header.read_text(), before.replace("#define MT6878_MD_ACK GENMASK(31, 30)",
                                                               "#define MT6878_MD_ACK BIT(30)"))
            # The recorded hardware ON value lacks ACK31 but has PWR_ON and ACK30.
            mask = (1 << 30) | (1 << 2)
            self.assertEqual(0x4200000d & mask, mask)
            self.assertNotEqual(0x4200000d & ((3 << 30) | 4), (3 << 30) | 4)

    def test_exact_board_delta(self):
        check.validate(*self.fixture())

    def test_reject_input_activation_and_counterfeit_final_marker(self):
        for node, prop, value in ((check.SUPPLIER, "status", b"okay\0"),
                                  (check.DOMAIN, "reg", hif_test.ints([1])),
                                  (check.NEMI, "status", b"okay\0"),
                                  (check.SUPPLIER, "nothing,modem-inherited-on-adoption", b""),
                                  ("/modem", "status", b"okay\0"),
                                  ("/display", "status", b"disabled\0"),
                                  ("/chosen", check.MARKERS[1], b"1\0")):
            normal, dt = self.fixture()
            dt[node][prop] = value
            with self.subTest(node=node, prop=prop), self.assertRaises(ValueError):
                check.validate(normal, dt)

    def test_paired_loader_refuses_wrong_profile_or_digest(self):
        import hashlib
        import io
        import struct
        import zipfile
        image = struct.pack("<II", 0x58881688, 16) + b"\xff" * (3 * 1024 * 1024 - 8)
        for fault in (None, "source", "profile", "hash", "duplicate"):
            manifest = dict(loader.PROFILE)
            if fault == "source":
                manifest["commit"] = "wrong"
            if fault == "profile":
                manifest["scp_secure"] = "disabled"
            digest = hashlib.sha256(image).hexdigest() if fault != "hash" else "0" * 64
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("BUILD-MANIFEST", "\n".join(k + "=" + v for k, v in manifest.items()))
                archive.writestr("SHA256SUMS", digest + "  u-boot-tetris-lk.img\n")
                archive.writestr("u-boot-tetris-lk.img", image)
                if fault == "duplicate":
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr("BUILD-MANIFEST", "ignored")
            if fault:
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    loader.checked_image(buffer.getvalue())
            else:
                self.assertEqual(loader.checked_image(buffer.getvalue())[1], digest)


if __name__ == "__main__":
    unittest.main()
