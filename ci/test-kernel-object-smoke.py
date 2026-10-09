#!/usr/bin/env python3
"""Input checks only: no compiler, downloads or hardware access."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("kernel-object-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name)
        commit = "a" * 40
        self.archive = f"linux-postmarketos-mediatek-mt6878-{commit}.tar.gz"
        (self.package / smoke.CONFIG).write_text("# test config\n")
        (self.package / "0001-test.patch").write_text("test patch\n")
        sums = "\n".join(
            hashlib.sha512((self.package / name).read_bytes()).hexdigest() + "  " + name
            for name in [smoke.CONFIG, "0001-test.patch"])
        self.source = (
            f'_commit="{commit}"\nsource="\n'
            '$pkgname-$_commit.tar.gz::https://github.com/MT6878-mainline/$_repository/archive/$_commit.tar.gz\n'
            '$_config\n0001-test.patch\n0002-test.patch.vendor\n"\n'
            f'sha512sums="\n{sums}\n' + "0" * 128 + f'  {self.archive}\n"\n')

    def write(self, source=None):
        (self.package / "APKBUILD").write_text(source or self.source)

    def test_package_order_and_vendor_exclusion(self):
        self.write()
        plan = smoke.plan(self.package)
        self.assertEqual(plan["patches"], ["0001-test.patch"])
        self.assertEqual(plan["archive"], self.archive)

    def test_modified_patch_fails(self):
        self.write()
        (self.package / "0001-test.patch").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            smoke.plan(self.package)

    def test_duplicate_patch_fails(self):
        self.write(self.source.replace("$_config\n", "$_config\n0001-test.patch\n"))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            smoke.plan(self.package)

    def test_duplicate_checksum_fails(self):
        self.write(self.source.replace('sha512sums="\n', 'sha512sums="\n' + "0" * 128 + f"  {self.archive}\n"))
        with self.assertRaisesRegex(ValueError, "duplicate package checksum"):
            smoke.plan(self.package)

    def test_mutable_source_fails(self):
        self.write(self.source.replace("a" * 40, "main"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            smoke.plan(self.package)

    def test_unknown_archive_expression_fails(self):
        self.write(self.source.replace("https://github.com/MT6878-mainline", "https://example.invalid"))
        with self.assertRaisesRegex(ValueError, "archive expression"):
            smoke.plan(self.package)

    def test_real_package_inputs(self):
        plan = smoke.plan(Path(__file__).resolve().parents[1] / smoke.PACKAGE)
        self.assertGreater(len(plan["patches"]), 100)
        self.assertEqual(len(plan["objects"]), 5)


if __name__ == "__main__":
    unittest.main()
