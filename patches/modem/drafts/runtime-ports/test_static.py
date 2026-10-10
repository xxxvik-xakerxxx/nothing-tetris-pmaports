#!/usr/bin/env python3
import ast
from pathlib import Path
import unittest
from check_runtime_ports import replace_once

HERE = Path(__file__).resolve().parent


class SourceTests(unittest.TestCase):
    def test_drift_rejected(self):
        for source in ('absent', 'old old'):
            with self.assertRaises(ValueError):
                replace_once(source, 'old', 'new')

    def test_python_syntax(self):
        for path in HERE.glob('*.py'):
            ast.parse(path.read_text())

    def test_no_execution_or_unowned_link_delete(self):
        source = (HERE / 'ccci_tetris_dependencies.h').read_text()
        for forbidden in ('device_link_del(', 'pm_runtime_get', 'ioremap(',
                          'arm_smccc', '->start(', 'ccci_md_start('):
            self.assertNotIn(forbidden, source)
        self.assertIn('DL_FLAG_AUTOREMOVE_CONSUMER', source)

    def test_actual_shape_and_producer_alignment(self):
        source = (HERE / 'ccci_tetris_dependencies.h').read_text()
        for expression in ('length != 32', 'raw + 16) != 2', 'raw + 20) != 21',
                           'base & 4095', 'used < 21 * 76'):
            self.assertIn(expression, source)

    def test_fixture_imports_actual_production_once(self):
        for component in ('dependencies', 'char_node'):
            self.assertEqual((HERE / f'test_{component}.c').read_text().count(
                '/* PRODUCTION */'), 1)


if __name__ == '__main__':
    unittest.main()
