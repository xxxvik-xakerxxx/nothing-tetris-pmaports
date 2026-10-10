#!/usr/bin/env python3
"""Offline fixture admission tests; never compile or execute firmware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import importlib.util
SPEC = importlib.util.spec_from_file_location('metadata_native', Path(__file__).with_name(
    'modem-metadata-native.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AdmissionTests(unittest.TestCase):
    def test_refuses_local_c(self):
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name(
            'modem-metadata-native.py')), '--vendor', '/unused', '--uboot', '/unused'],
            env=dict(os.environ, CI='false', GITHUB_ACTIONS='false'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('GitHub CI-only', result.stderr)

    def test_stock_identity_bound_to_extraction_and_bytes(self):
        stock = MODULE.load('test_metadata_stock', MODULE.ROOT / 'ci/extract-stock-modem.py')
        evidence = {'release': stock.RELEASE, 'archive_sha256': stock.ARCHIVE_SHA256,
                    'sha256': stock.IMAGE_SHA256, 'size': 4}
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'md1img.bin').write_bytes(b'test')
            manifest = directory / 'BUILD-MANIFEST.json'
            manifest.write_text(json.dumps(evidence))
            with self.assertRaises(ValueError):
                MODULE.verify_stock(directory)
            with patch.object(MODULE, 'digest', return_value=stock.IMAGE_SHA256):
                self.assertEqual(MODULE.verify_stock(directory)[1], evidence)
                for key in evidence:
                    malformed = dict(evidence, **{key: 'wrong'})
                    manifest.write_text(json.dumps(malformed))
                    with self.subTest(field=key), self.assertRaises(ValueError):
                        MODULE.verify_stock(directory)


if __name__ == '__main__':
    unittest.main()
