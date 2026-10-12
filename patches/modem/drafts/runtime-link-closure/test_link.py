#!/usr/bin/env python3
"""Source-only linker boundary tests; no native compiler or kernel execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_link', HERE / 'link_full.py')
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


class LinkTests(unittest.TestCase):
    def test_dependency_spelling(self):
        self.assertEqual(link.dependency_names('ccci_util_lib,mt6878-ccci-start,ccmni'),
                         {'ccci_util_lib', 'mt6878_ccci_start', 'ccmni'})
        self.assertEqual(link.dependency_names(''), set())

    def test_preflight_failure_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'link'
            argv = ['link_full.py', '--vendor', temp, '--destination', str(destination)]
            with patch('sys.argv', argv), patch.object(link, 'build_ci',
                    side_effect=ValueError('provider hash mismatch')):
                with self.assertRaisesRegex(ValueError, 'provider hash mismatch'):
                    link.main()
            result = json.loads((destination / 'full-link.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['error'], 'provider hash mismatch')
            self.assertFalse((destination / 'artifacts').exists())

    def test_existing_destination_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'link'
            destination.mkdir()
            previous = destination / 'full-link.json'
            previous.write_text('previous')
            argv = ['link_full.py', '--vendor', temp, '--destination', str(destination)]
            with patch('sys.argv', argv), patch.object(link, 'build_ci') as build:
                with self.assertRaises(FileExistsError):
                    link.main()
                build.assert_not_called()
            self.assertEqual(previous.read_text(), 'previous')


if __name__ == '__main__':
    unittest.main()
