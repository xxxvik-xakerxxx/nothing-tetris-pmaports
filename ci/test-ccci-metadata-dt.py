#!/usr/bin/env python3
"""Pure DT-property fixtures; no compilation or physical access."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('metadata_dt', Path(__file__).with_name('check-ccci-metadata-dt.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MetadataDT(unittest.TestCase):
    def baseline(self):
        return {'/': {}, '/modem': dict(module.EXPECTED)}

    def test_disabled_metadata_anchor(self):
        module.validate(self.baseline())

    def test_missing_duplicate_and_children_rejected(self):
        cases = ({'/': {}}, {**self.baseline(), '/other': dict(module.EXPECTED)},
                 {**self.baseline(), '/modem/child': {}})
        for tree in cases:
            with self.subTest(tree=tree), self.assertRaises(ValueError):
                module.validate(tree)

    def test_enable_resources_descriptor_and_wrong_profile_rejected(self):
        for name, value in (('status', b'okay\0'), ('reg', b'\0' * 16),
                ('interrupts', b'\0' * 12), ('power-domains', b'\0' * 8),
                ('ccci,modem_info_v2', b'\0' * 32), ('ccci,modem_info', b'\0' * 16),
                ('mediatek,md-generation', (6298).to_bytes(4, 'big'))):
            tree = self.baseline()
            tree['/modem'][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                module.validate(tree)

    def test_inherited_tag_allocation_rejected(self):
        tree = self.baseline()
        tree['/reserved-memory/tetris-modem-linux-tags'] = {}
        with self.assertRaises(ValueError):
            module.validate(tree)

    def test_phandle_aliases_do_not_change_payload(self):
        tree = self.baseline()
        before = copy.deepcopy(tree)
        tree['/modem']['phandle'] = b'\0\0\0\1'
        module.validate(tree)
        self.assertEqual(before['/modem'], module.EXPECTED)


if __name__ == '__main__':
    unittest.main()
