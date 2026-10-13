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
            self.assertIn("pkgrel=183\n", apk)
            self.assertIn('die "native MD diagnostic exclusion unresolved: $_symbol"', apk)
            self.assertLess(apk.index("0180-native-md"), apk.index("0181-native-camera"))
            self.assertEqual(result["source_commit"], stage.SOURCE)
            self.assertFalse(result["modem_consumer_enabled"])
            config = (tree / stage.KERNEL / "config-postmarketos-mediatek-mt6878.aarch64").read_text()
            for name in stage.DISABLED:
                self.assertIn("# CONFIG_" + name + " is not set\n", config)
            for name in stage.ENABLED:
                self.assertIn("CONFIG_" + name + "=y\n", config)
            self.assertIn(stage.BOARD, (tree / stage.DEVICE / "deviceinfo").read_text())

    def test_board_patch_applies_without_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            makefile = tree / "arch/arm64/boot/dts/mediatek/Makefile"
            makefile.parent.mkdir(parents=True)
            makefile.write_text("# SPDX-License-Identifier: GPL-2.0\ndtb-$(CONFIG_ARCH_MEDIATEK) += mt2712-evb.dtb\n")
            subprocess.run(["git", "apply", "--verbose", "-"], input=stage.dt_patch(),
                           cwd=tree, text=True, check=True, capture_output=True)
            self.assertTrue((makefile.parent / (stage.BOARD + ".dts")).is_file())

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
