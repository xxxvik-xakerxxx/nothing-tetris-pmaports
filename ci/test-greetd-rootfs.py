#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gate', Path(__file__).with_name('check-greetd-rootfs.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def test_actual_identity(self):
        self.assertEqual(gate.identity('greetd:x:113:119:greetd:/var/lib/greetd:/sbin/nologin',
                                       'greetd:x:119:'), (113, 119))

    def test_dynamic_uid(self):
        self.assertEqual(gate.identity('greetd:x:117:123::/var/lib/greetd:/sbin/nologin',
                                       'greetd:x:123:'), (117, 123))

    def test_bad_identity(self):
        for passwd, group in [('', ''), ('greetd:x:0:119::/var/lib/greetd:/bin/sh', 'greetd:x:119:'),
                              ('greetd:x:113:119::/var/lib/greetd:/bin/sh', 'greetd:x:113:'),
                              ('greetd:x:113:119::/wrong:/bin/sh', 'greetd:x:119:')]:
            with self.subTest(passwd=passwd), self.assertRaises(ValueError):
                gate.identity(passwd, group)

    def metadata(self, uid=113, owner=113, group=113, mode=0o700, parent=(0o750, 113, 119)):
        def info(path):
            if str(path).endswith('/dconf'):
                values = mode, owner, group
            elif str(path).endswith('/greetd'):
                values = parent
            else:
                values = 0o755, 0, 0
            return SimpleNamespace(st_mode=stat.S_IFDIR | values[0], st_uid=values[1], st_gid=values[2])
        with patch.object(Path, 'lstat', info):
            gate.check_metadata(Path('/fixture'), uid, 119)

    def test_packaged_old_gid_usable(self):
        self.metadata()

    def test_tmpfiles_gid_also_usable(self):
        self.metadata(group=119)

    def test_dynamic_owner_usable(self):
        self.metadata(uid=117, owner=117, parent=(0o750, 117, 119))

    def test_wrong_owner_rejected(self):
        with self.assertRaisesRegex(ValueError, 'owner UID 117'):
            self.metadata(uid=117)

    def test_modes_rejected(self):
        for mode in (0o500, 0o600, 0o750, 0o770, 0o777):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.metadata(mode=mode)

    def test_unsearchable_parent(self):
        with self.assertRaisesRegex(ValueError, 'not searchable'):
            self.metadata(parent=(0o700, 0, 0))

    def test_group_parent_search(self):
        self.metadata(parent=(0o750, 0, 119))

    @unittest.skipUnless(os.geteuid() == 0 and hasattr(os, 'chroot'), 'requires Linux root fixture')
    def test_real_access_without_target_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            target = root / gate.DCONF.lstrip('/')
            target.mkdir(parents=True)
            os.chown(root / 'var/lib/greetd', 113, 119)
            (root / 'var/lib/greetd').chmod(0o750)
            os.chown(target, 113, 113)
            target.chmod(0o700)
            gate.check_metadata(root, 113, 119)
            gate.check_access(root, 113, 119)
            with self.assertRaises(ValueError):
                gate.check_access(root, 117, 119)
            self.assertEqual(list(target.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
