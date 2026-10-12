#!/usr/bin/env python3
"""Real libarchive fixtures; no compilation, firmware, device or extraction."""
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BSDTAR = shutil.which('bsdtar') or ('/usr/bin/tar' if os.uname().sysname == 'Darwin' else None)


@unittest.skipUnless(BSDTAR, 'libarchive tar is required for archive fixtures')
class Initramfs(unittest.TestCase):
    def fixture(self, directory, module=True, selection=True):
        root = Path(directory) / 'root'
        root.mkdir()
        files = {'usr/share/deviceinfo/device-nothing-tetris':
                 'deviceinfo_usb_network_function="' + ('ncm.usb0' if selection else 'rndis.usb0') + '"\n'}
        if module:
            files['usr/lib/modules/6.18.0/kernel/drivers/usb/gadget/function/usb_f_ncm.ko'] = 'fixture module'
        for name, value in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        archive = Path(directory) / 'initramfs'
        subprocess.run([BSDTAR, '--format=newc', '-cf', str(archive), '-C', str(root), *files], check=True)
        return archive

    def check(self, archive, success=True, release='6.18.0', executable=BSDTAR):
        result = subprocess.run(['sh', str(ROOT / 'scripts/check-initramfs.sh'), str(archive), release],
                                env=dict(os.environ, BSDTAR=executable), capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_uncompressed_and_gzip(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.fixture(directory)
            self.check(archive)
            archive.write_bytes(gzip.compress(archive.read_bytes()))
            self.check(archive)
            self.check(archive, success=False, release='other-release')

    @unittest.skipUnless(shutil.which('zstd'), 'zstd fixtures require the standard compressor')
    def test_zstd_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.fixture(directory)
            packed = subprocess.check_output(['zstd', '-q', '--check', '-c', str(archive)])
            archive.write_bytes(packed)
            self.check(archive)
            archive.write_bytes(packed[:len(packed) // 2])
            self.check(archive, success=False)

    def test_missing_module_or_selection(self):
        for module, selection in ((False, True), (True, False)):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as directory:
                self.check(self.fixture(directory, module, selection), success=False)

    def test_invalid_archive_and_tool_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'invalid'
            archive.write_text('not an archive')
            self.check(archive, success=False)
            self.check(archive, success=False, executable='/usr/bin/false')

    def test_ci_does_not_assume_initramfs_gzip(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('libarchive-tools', workflow)
        self.assertIn('check-initramfs.sh "$rootfs/boot/initramfs" "$release"', workflow)
        self.assertNotIn('gzip -cd "$rootfs/boot/initramfs"', workflow)


if __name__ == '__main__':
    unittest.main(verbosity=2)
