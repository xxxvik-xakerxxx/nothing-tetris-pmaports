#!/usr/bin/env python3
"""Pinned patch/ABI/ownership checks only; no kernel/native build or device IO."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODULES = Path(os.environ.get("TETRIS_MODULES_TREE",
                             ROOT / "upstream/android_kernel_modules_nothing_mt6878")).resolve()
DEVICE = Path(os.environ.get("TETRIS_DEVICE_MODULES_TREE",
                            ROOT / "upstream/android_kernel_device_modules_6.1_nothing_mt6878")).resolve()
PACKAGE = HERE.parents[1] / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
COMPAT_NAMES = (
    "1002-vendor-gnss-linux-6.18-compat.patch.vendor",
    "1003-vendor-gnss-v051-readonly-uapi.patch.vendor",
    "1004-vendor-gnss-finalize-fsm-records.patch.vendor",
    "1005-vendor-gnss-propagate-clock-read-error.patch.vendor",
)
MODULE_PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEVICE_PIN = "ee2be53cb75670b548948636a0db1d1ff112bf12"
PLAT = "connectivity/gps/data_link/linux/gps_dl_linux_plat_drv.c"
IOCTL = "connectivity/gps/gps_mcudl/linux/gps_mcudl_each_device.c"
HEADER = "connectivity/gps/data_link/linux/inc/gps_dl_lna_metadata.h"


def source(repo, pin, path):
    # Preserve source CRLF until the package's explicit pre-1005 normalization.
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{pin}:{path}"]).decode()


def apply_patch(directory, path, allow_offset=False):
    result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(path)],
                            cwd=directory, text=True, capture_output=True,
                            env={**os.environ, "LC_ALL": "C"})
    diagnostics = result.stdout + result.stderr
    if result.returncode or re.search(r"fuzz", diagnostics, re.I):
        raise AssertionError(f"{path.name}:\n{diagnostics}")
    if not allow_offset and re.search(r"offset", diagnostics, re.I):
        raise AssertionError(f"{path.name}: unexpected relocation:\n{diagnostics}")
    return diagnostics


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = (HERE / "0002-gps-mcudl-query-owned-lna-metadata.patch").read_text()
        cls.added = "\n".join(line[1:] for line in cls.patch.splitlines()
                              if line.startswith("+") and not line.startswith("+++"))
        cls.fixed = {}
        with tempfile.TemporaryDirectory(prefix="gnss-lna-metadata-") as directory:
            # Patch fixtures only. These are disposable files, not repo edits.
            paths = re.findall(r"^--- a/(.+)$", cls.patch, re.M)
            for name in paths:
                dest = Path(directory) / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(source(MODULES, MODULE_PIN, name))
            apply_patch(directory, HERE / "0002-gps-mcudl-query-owned-lna-metadata.patch")
            for name in paths + [HEADER]:
                cls.fixed[name] = (Path(directory) / name).read_text()
        cls.stacked = {}
        cls.stack_diagnostics = []
        with tempfile.TemporaryDirectory(prefix="gnss-lna-compat-stack-") as directory:
            stack = [PACKAGE / name for name in COMPAT_NAMES]
            all_paths = set(paths)
            for path in stack:
                all_paths.update(re.findall(r"^--- a/(.+)$", path.read_text(), re.M))
            for name in sorted(all_paths):
                dest = Path(directory) / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(source(MODULES, MODULE_PIN, name).encode())
            for path in stack:
                if path.name.startswith("1005-"):
                    clock = Path(directory) / "connectivity/gps/data_link/linux/gps_dl_linux_clock_mng.c"
                    clock.write_bytes(clock.read_bytes().replace(b"\r\n", b"\n"))
                cls.stack_diagnostics.append(apply_patch(directory, path, allow_offset=True))
            # 1002 removes one platform-driver line. Candidate relocation is
            # expected; every hunk must still match fully, without fuzz.
            cls.stack_diagnostics.append(apply_patch(
                directory, HERE / "0002-gps-mcudl-query-owned-lna-metadata.patch", allow_offset=True))
            for name in all_paths | {HEADER}:
                cls.stacked[name] = (Path(directory) / name).read_text()

    def test_decoder_exact_binding(self):
        binding = source(DEVICE, DEVICE_PIN, "include/dt-bindings/pinctrl/mt6878-pinfunc.h")
        expected = {(int(pin), int(func)) for pin, func in re.findall(
            r"#define PINMUX_GPIO\d+__FUNC_GPS_L1_ELNA_EN \(MTK_PIN_NO\((\d+)\) \| (\d+)\)", binding)}
        actual = {(int(pin), int(func)) for pin, func in re.findall(
            r"case \((\d+)u << 8\) \| (\d+)u:", self.fixed[HEADER])}
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual), 7)
        self.assertEqual(self.fixed[HEADER], (HERE / "gps_dl_lna_metadata.h").read_text())

    def test_full_package_stack_then_candidate(self):
        self.assertEqual(len(self.stack_diagnostics), 5)
        self.assertEqual(self.stacked[HEADER], self.fixed[HEADER])
        start = "/* Cached metadata follows"
        end = "bool gps_dl_get_iomem_by_name"
        self.assertEqual(self.stacked[PLAT].split(start, 1)[1].split(end, 1)[0],
                         self.fixed[PLAT].split(start, 1)[1].split(end, 1)[0])
        self.assertIn("static void gps_dl_remove", self.stacked[PLAT])
        clock = self.stacked["connectivity/gps/data_link/linux/gps_dl_linux_clock_mng.c"]
        self.assertIn("retval = regmap_read", clock)
        self.assertIn("return retval;", clock)
        self.assertIn("gps_dl_get_lna_pin(&gps_lna_pin)", self.stacked[IOCTL])

    def test_injected_checkout_paths_do_not_fall_back(self):
        with tempfile.TemporaryDirectory(prefix="gnss-ci-paths-") as directory:
            modules = Path(directory) / "android-kernel-modules"
            device = Path(directory) / "android-kernel-device-modules"
            # Import only: deliberately nonexistent paths must be retained,
            # never replaced by a convenient local checkout.
            command = ("import json,runpy; m=runpy.run_path(" + repr(str(Path(__file__).resolve())) +
                       "); print(json.dumps([str(m['MODULES']), str(m['DEVICE'])]))")
            actual = subprocess.check_output([sys.executable, "-c", command], text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                     "TETRIS_MODULES_TREE": str(modules),
                     "TETRIS_DEVICE_MODULES_TREE": str(device)})
            self.assertEqual(json.loads(actual), [str(modules.resolve()), str(device.resolve())])

    def test_no_new_hardware_control(self):
        for forbidden in ("pinctrl_select_state", "gpiod_", "gpio_request", "gpio_set",
                          "regulator_", "writel", "ioremap", "mtk_wmt_get_gps_lna_pin_num"):
            self.assertNotIn(forbidden, self.added)

    def test_readonly_owner_and_validation(self):
        for fragment in ('"gps_l1_lna_dsp_ctrl"', '"mediatek,mt6878-gps"',
                         '"mediatek,mt6878-pinctrl"', '"pinmux") != 1',
                         'property) != 1', '++count != 1', '-ENODATA', '-ENODEV',
                         'gps_dl_lna_metadata_owner != dev', 'gps_dl_lna_metadata_error = -ENODEV',
                         'gps_dl_lna_metadata_conflict = true',
                         'gps_dl_lna_metadata_conflict ? -EBUSY : -ENODEV'):
            self.assertIn(fragment, self.added)
        self.assertIn('gps_dl_lna_metadata_init(&pdev->dev);', self.fixed[PLAT])
        self.assertIn('gps_dl_lna_metadata_remove(&pdev->dev);', self.fixed[PLAT])
        self.assertIn('if (retval)\n\t\t\tbreak;', self.fixed[IOCTL])
        self.assertIn('compat_ptr(arg)', self.fixed[IOCTL])

    def test_conflict_reset_only_after_unregister(self):
        fixed = self.fixed[PLAT]
        self.assertEqual(fixed.count('gps_dl_lna_metadata_reset();'), 1)
        self.assertIn('platform_driver_unregister(&gps_dl_dev_drv);\n\t'
                      'gps_dl_lna_metadata_reset();', fixed)
        init = fixed[fixed.index('static void gps_dl_lna_metadata_init'):fixed.index('static void gps_dl_lna_metadata_remove')]
        self.assertIn('if (gps_dl_lna_metadata_conflict) {\n\t\tret = -EBUSY;\n\t\t'
                      'gps_dl_lna_metadata_error = ret;', init)
        self.assertNotIn('gps_dl_lna_metadata_conflict = false', init)

    def test_no_vendor_board_default(self):
        base = source(DEVICE, DEVICE_PIN, "arch/arm64/boot/dts/mediatek/k6878v1_64.dts")
        block = base.index('/* GPS GPIO standardization start */')
        self.assertLess(base.rfind('#if 0', 0, block), block)
        self.assertIn('#endif', base[base.index('/* GPS GPIO standardization end */'):])
        tetris = source(DEVICE, DEVICE_PIN, "arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts")
        self.assertIn('#include "k6878v1_64.dts"', tetris)
        self.assertNotIn('gps_l1_lna', tetris)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-owner-fixture":
        MetadataTests.setUpClass()
        fixed = MetadataTests.stacked[PLAT]
        start = fixed.index("/* Cached metadata follows")
        end = fixed.index("bool gps_dl_get_iomem_by_name", start)
        Path(sys.argv[2]).write_text(fixed[start:end])
    else:
        unittest.main()
