#!/usr/bin/env python3
"""Static complete-stack checks only; no local compiler or hardware calls."""
import ast
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import check_lifecycle as lifecycle

VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', lifecycle.HERE.parents[4] /
    'android_kernel_device_modules_6.1_nothing_mt6878'))


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.old, cls.new = lifecycle.build(VENDOR)

    def test_exact_overlay_apply(self):
        self.assertEqual(self.patch,
            (lifecycle.HERE / 'runtime-lifecycle.patch.vendor').read_text())
        lifecycle.apply_check(self.patch, self.old)

    def test_denial_precedes_physical_dispatch(self):
        for name, value in lifecycle.ENTRIES.items():
            body = lifecycle.function(self.new, name)[0]
            deny = 'return' + (' ' + value if value else '') + ';'
            self.assertLess(body.index(deny), body.index('#endif'))
            for operation in ('ccci_get_modem()', 'container_of(attr,'):
                if operation in body:
                    self.assertLess(body.index(deny), body.index(operation))
            self.assertIn('#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)', body)

    def test_only_four_entries_changed(self):
        old, new = self.old, self.new
        for name in lifecycle.ENTRIES:
            old = old.replace(lifecycle.function(old, name)[0], name)
            new = new.replace(lifecycle.function(new, name)[0], name)
        self.assertEqual(old, new)
        self.assertNotIn('register_prepare.h', self.patch)

    def test_full_shipping_stack(self):
        objects = lifecycle.load('lifecycle_object_stage',
            lifecycle.HERE.parent / 'runtime-object-ci/check_objects.py')
        data, _, package = objects.plan()
        with tempfile.TemporaryDirectory(prefix='lifecycle-complete-static-') as temp:
            root = Path(temp) / 'vendor'
            with contextlib.redirect_stdout(io.StringIO()):
                objects.stage_vendor(VENDOR, root, package, data)
            self.assertEqual((root / lifecycle.SOURCE).read_text(), self.new)
            subprocess.run(['git', 'apply', '--reverse', '--check', '-'], input=self.patch,
                           cwd=root, text=True, check=True)
            subprocess.run(['git', 'apply', '--reverse', '-'], input=self.patch,
                           cwd=root, text=True, check=True)
            self.assertEqual((root / lifecycle.SOURCE).read_text(), self.old)
            subprocess.run(['git', 'apply', '--check', '-'], input=self.patch,
                           cwd=root, text=True, check=True)
            subprocess.run(['git', 'apply', '-'], input=self.patch,
                           cwd=root, text=True, check=True)
            self.assertEqual((root / lifecycle.SOURCE).read_text(), self.new)

    def test_drift_refused(self):
        with self.assertRaises(ValueError):
            lifecycle.guard(self.old.replace('int ccci_modem_syssuspend(void)',
                'int ccci_modem_syssuspend_changed(void)'), 'ccci_modem_syssuspend', '0')

    def test_native_refused_outside_ci(self):
        from unittest.mock import patch
        with patch.dict(os.environ, CI='false', GITHUB_ACTIONS='false'):
            with self.assertRaisesRegex(ValueError, 'GitHub CI-only'):
                lifecycle.native_ci(self.new)

    def test_fixture_uses_actual_functions(self):
        fixture = (lifecycle.HERE / 'test_callbacks.c').read_text()
        self.assertEqual(fixture.count('/* PRODUCTION */'), 1)
        for path in lifecycle.HERE.glob('*.py'):
            ast.parse(path.read_text())
        # Use the existing lexical C delimiter check, never a local compilation.
        owner = lifecycle.load('lifecycle_owner_check',
            lifecycle.HERE.parents[1] / 'check_transport_owner.py')
        production = '\n'.join(lifecycle.function(self.new, name)[0]
                               for name in lifecycle.ENTRIES)
        owner.check_delimiters(fixture.replace('/* PRODUCTION */', production))


if __name__ == '__main__':
    unittest.main()
