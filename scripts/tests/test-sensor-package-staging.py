#!/usr/bin/env python3
"""Check the real overlay staging path without applying unrelated patches."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "integrations/sensor-proxy"


class SensorPackageStaging(unittest.TestCase):
    def test_all_local_package_sources_are_staged_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            # Git is only used to recognize already-applied unrelated patches.
            tools = tree / "tools"
            tools.mkdir()
            git = tools / "git"
            git.write_text("#!/bin/sh\nexit 0\n")
            git.chmod(0o755)
            initramfs = tree / "main/postmarketos-initramfs/tests"
            initramfs.mkdir(parents=True)
            (initramfs.parent / "APKBUILD").write_text("pkgver=3.12.3\n")
            (initramfs / "01-parse-cmdline-testlib.sh").touch()
            (initramfs.parent / "init_functions.sh").write_text(
                "derive_usb_network_mac_pair() { :; }\n")
            (tree / "deviceinfo_schema.toml").write_text(
                "[variable.usb.usb_network_mac_seed_path]\n")
            stable = initramfs / "03-usb-stable-mac-testlib.sh"
            stable.touch()
            stable.chmod(0o755)
            subprocess.run(
                ["sh", str(ROOT / "scripts/apply-pmaports-patches.sh"), str(tree)],
                env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]},
                check=True, capture_output=True, text=True)
            staged = tree / "device/testing/iio-sensor-proxy-tetris"
            self.assertEqual((staged / "APKBUILD").read_bytes(),
                             (SOURCE / "APKBUILD").read_bytes())
            sums = re.search(r'^sha512sums="\n(.*?)^"$',
                             (SOURCE / "APKBUILD").read_text(), re.M | re.S)
            self.assertIsNotNone(sums)
            for line in sums.group(1).splitlines():
                _, name = line.split()
                if name.endswith(".tar.gz"):
                    continue
                with self.subTest(source=name):
                    self.assertEqual((staged / name).read_bytes(),
                                     (SOURCE / name).read_bytes())
            self.assertTrue((staged / "net.hadess.SensorProxy.service").is_file())


if __name__ == "__main__":
    unittest.main()
