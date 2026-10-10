#!/usr/bin/env python3
"""Offline path/selection/source-pin fixtures; never import the emulator."""
import ast
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

from b41_xml_read_profile import (PRIMARY, PREFERRED, UnresolvedProfile,
    scan_document, select_documents, source_profile)

ASSETS = None


def document(version):
    return f'<mnl_config version="{version}" type="gps">\n'.encode()


def cases(stock):
    return (
        ("missing-data", stock, None, PRIMARY, 7),
        ("tie", stock, stock, PREFERRED, 3),
        ("older-data", stock, document("21111600.6.00.00"), PRIMARY, 7),
        ("same-date-later-revision", stock, document("21111601.99.00.99"), PREFERRED, 3),
        ("newer-data", stock, document("21111602.6.00.00"), PREFERRED, 3),
        ("missing-primary", None, stock, PREFERRED, 3),
        ("both-missing", None, None, PRIMARY, 7),
        ("empty-data", stock, b"", PRIMARY, 7),
        ("empty-primary", b"", stock, PREFERRED, 3),
        ("both-empty", b"", b"", PREFERRED, 3),
        ("unknown-code-newer-data", stock, document("21111602.6.ZZ.00"), PREFERRED, 3),
    )


class ProfileTests(unittest.TestCase):
    def test_real_pins_slices_and_machine_readable_paths(self):
        profile = source_profile(*ASSETS)
        self.assertEqual(json.loads(json.dumps(profile)), profile)
        self.assertEqual(profile["paths"]["primary"], PRIMARY)
        self.assertEqual(profile["paths"]["preferred"], PREFERRED)
        self.assertEqual(profile["version"]["pinned_primary"]["compared_version"], 21111601)
        self.assertEqual(profile["version"]["pinned_primary"]["status"], 1)
        self.assertIsNone(profile["runtime_preferred_scan"])

    def test_selector_fixtures(self):
        stock = ASSETS[2].read_bytes()
        for name, primary, preferred, path, policy in cases(stock):
            with self.subTest(name=name):
                result = select_documents(primary, preferred)
                self.assertEqual((result.read_path, result.policy), (path, policy))
                self.assertEqual(result.write_path, PREFERRED)

    def test_missing_is_not_empty_or_validity(self):
        self.assertEqual(scan_document(None).status, 0)
        self.assertEqual(scan_document(b"").status, 8)
        self.assertEqual(scan_document(b"unrelated\n").status, 8)
        self.assertEqual(scan_document(b"<mnl_config version=\n").status, 8)
        for index, code in enumerate(("00", "0O", "0L", "0S", "0H", "0V", "AB"), 1):
            self.assertEqual(scan_document(document("21111601.6." + code)).status, index)
        unsupported = scan_document(document("21111601.6.ZZ"))
        self.assertEqual((unsupported.status, unsupported.compared_version), (8, 21111601))

    def test_unsupported_stdio_and_atof_contracts_refuse(self):
        for raw in (b"\0", b"x" * 1024, b"x\n" * 1025,
                    document("NaN.6.00"), document("21111601x.6.00"),
                    document("21111601..00"), document("21111601.6.0"),
                    b'<mnl_config version="21111601.6.00"  type="gps">\n',
                    b'type= <mnl_config version="21111601.6.00" type="gps">\n'):
            with self.subTest(raw=raw[:70]):
                with self.assertRaises(UnresolvedProfile):
                    scan_document(raw)

    def test_foreign_xml_does_not_get_promoted_to_stock(self):
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "MNL_Config.xml"
            wrong.write_bytes(document("21111601.6.00.00"))
            with self.assertRaisesRegex(ValueError, "pinned XML"):
                source_profile(ASSETS[0], ASSETS[1], wrong)

    def test_oracle_deferred_import_and_ast(self):
        here = Path(__file__).resolve().parent
        for name in ("b41_xml_read_profile.py", "test_b41_xml_read_profile_oracle.py"):
            tree = ast.parse((here / name).read_text())
            for statement in tree.body:
                if isinstance(statement, (ast.Import, ast.ImportFrom)):
                    module = getattr(statement, "module", "") or ""
                    self.assertNotIn("unicorn", module)
                    self.assertNotIn("test_b41_startup", module)
        result = subprocess.run([sys.executable, str(here / "test_b41_xml_read_profile_oracle.py")],
            env=dict(os.environ, CI="false", PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linux CI-only", result.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_b41_xml_read_profile.py libmnl.so mnld MNL_Config.xml")
    ASSETS = tuple(map(Path, sys.argv[1:]))
    unittest.main(argv=[sys.argv[0]])
