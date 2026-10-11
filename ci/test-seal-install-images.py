#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'sealer', Path(__file__).with_name('seal-install-images.py'))
sealer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sealer)
NATIVE = '--native-fixtures' in sys.argv
if NATIVE:
    sys.argv.remove('--native-fixtures')


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / 'root.img'
        self.image.write_bytes(b'fixture')

    def test_file_admission(self):
        self.assertEqual(sealer.image_path(self.image), self.image.resolve())
        link = self.image.with_name('link.img')
        link.symlink_to(self.image)
        empty = self.image.with_name('empty.img')
        empty.touch()
        for value in (link, empty, self.image.parent):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sealer.image_path(value)

    def test_loop_and_hardlink_rejected(self):
        alias = self.image.with_name('alias.img')
        alias.hardlink_to(self.image)
        for backing in (self.image, alias, str(self.image) + ' (deleted)'):
            with self.subTest(backing=backing), self.assertRaisesRegex(ValueError, 'attached'):
                sealer.check_detached([self.image], {'loopdevices': [
                    {'name': '/dev/loop7', 'back-file': str(backing)}]})

    def test_unknown_inventory_rejected(self):
        for inventory in ({}, {'loopdevices': None}, {'loopdevices': [{}]},
                          {'loopdevices': [{'back-file': 'relative.img'}]}):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                sealer.check_detached([self.image], inventory)
        sealer.check_detached([self.image], {'loopdevices': []})

    def test_detachment_precedes_any_fsck(self):
        inventory = {'loopdevices': [{'name': 'loop7', 'back-file': str(self.image)}]}
        with patch.object(sealer.subprocess, 'check_output', return_value=json.dumps(inventory)), \
                patch.object(sealer, 'command') as execute, self.assertRaises(ValueError):
            sealer.seal([self.image])
        execute.assert_not_called()

    def test_duplicate_identity_precedes_inventory(self):
        with patch.object(sealer.subprocess, 'check_output') as query, \
                self.assertRaisesRegex(ValueError, 'duplicate'):
            sealer.seal([self.image, self.image])
        query.assert_not_called()

    def test_fsck_status_policy(self):
        for status in (0, 1, 2, 3, 4, 8, 16, 32, 128, -9):
            with self.subTest(status=status), patch.object(sealer.subprocess, 'run',
                    return_value=subprocess.CompletedProcess(['e2fsck'], status)):
                if status in (0, 1):
                    self.assertEqual(sealer.command(['e2fsck'], (0, 1)), status)
                else:
                    with self.assertRaises(ValueError):
                        sealer.command(['e2fsck'], (0, 1))
                if status != 0:
                    with self.assertRaises(ValueError):
                        sealer.command(['e2fsck'])

    def test_extent_change_rejected(self):
        def execute(argv, allowed=(0,)):
            if argv[0] == 'resize2fs':
                self.image.write_bytes(b'changed extent')
            return 0
        with patch.object(sealer.subprocess, 'check_output', return_value='{"loopdevices":[]}'), \
                patch.object(sealer, 'command', side_effect=execute), \
                self.assertRaisesRegex(ValueError, 'extent mismatch'):
            sealer.seal([self.image])

    def test_readonly_failure_stops_before_resize(self):
        calls = []

        def execute(argv, allowed=(0,)):
            calls.append(argv)
            if argv[:3] == ['e2fsck', '-f', '-n']:
                raise ValueError('verification failed')
            return 0

        with patch.object(sealer.subprocess, 'check_output', return_value='{"loopdevices":[]}'), \
                patch.object(sealer, 'command', side_effect=execute), \
                self.assertRaisesRegex(ValueError, 'verification failed'):
            sealer.seal([self.image])
        self.assertFalse(any(argv[0] == 'resize2fs' for argv in calls))

    def test_ci_seals_before_conversion_and_hashes(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml').read_text()
        install = workflow.split('- name: Build install images\n', 1)[1].split(
            '- name: Build isolated read-only diagnostic boot artifacts\n', 1)[0]
        self.assertLess(install.index('shutdown\n'), install.index('seal-install-images.py'))
        self.assertLess(install.index('seal-install-images.py'), install.index('img2simg '))
        self.assertLess(install.index('img2simg '), install.index('> SHA256SUMS'))
        self.assertIn('image_sealing=offline-forced-fsck-and-unforced-resize-check-v1', install)
        self.assertIn('/work/out/logs/install-image-seal.log', install)
        diagnostics = workflow.split('- name: Build isolated read-only diagnostic boot artifacts\n',
                                     1)[1].split('- name: Upload isolated read-only diagnostics', 1)[0]
        self.assertNotIn('rootfs_nothing-tetris', diagnostics)
        self.assertIn('/work/checked-dtbs/', diagnostics)

    @unittest.skipUnless(NATIVE, 'real ext image fixtures run in CI only')
    def test_real_fsck_sparse_roundtrip_and_unforced_growth(self):
        for tool in ('mkfs.ext2', 'mkfs.ext4', 'debugfs', 'e2fsck', 'resize2fs',
                     'dumpe2fs', 'img2simg', 'simg2img', 'losetup'):
            self.assertIsNotNone(shutil.which(tool), tool)
        for kind in ('ext2', 'ext4'):
            with self.subTest(kind=kind):
                with self.image.open('wb') as stream:
                    stream.truncate(64 * 1024 * 1024)
                subprocess.run(['mkfs.' + kind, '-F', '-b', '4096', str(self.image)], check=True)
                subprocess.run(['debugfs', '-w', '-R', 'set_super_value lastcheck 1',
                                str(self.image)], check=True)
                subprocess.run(['debugfs', '-w', '-R', 'set_super_value mtime 2',
                                str(self.image)], check=True)
                refusal = subprocess.run(['resize2fs', str(self.image)], capture_output=True)
                self.assertNotEqual(refusal.returncode, 0)
                self.assertIn(b'e2fsck -f', refusal.stderr)
                sealer.seal([self.image])
                packed = self.image.with_suffix('.sparse')
                expanded = self.image.with_name('expanded.img')
                subprocess.run(['img2simg', str(self.image), str(packed)], check=True)
                subprocess.run(['simg2img', str(packed), str(expanded)], check=True)
                self.assertEqual(self.image.read_bytes(), expanded.read_bytes())
                with expanded.open('r+b') as stream:
                    stream.truncate(128 * 1024 * 1024)
                subprocess.run(['resize2fs', str(expanded)], check=True)
                sealer.command(['e2fsck', '-f', '-n', str(expanded)])
                header = subprocess.check_output(['dumpe2fs', '-h', str(expanded)], text=True,
                                                 env={**sealer.os.environ, 'LC_ALL': 'C'})
                fields = dict(line.split(':', 1) for line in header.splitlines() if ':' in line)
                self.assertEqual(int(fields['Block count']) * int(fields['Block size']),
                                 128 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
