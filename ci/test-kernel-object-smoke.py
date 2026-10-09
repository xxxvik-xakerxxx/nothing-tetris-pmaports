#!/usr/bin/env python3
"""Input checks only: no compiler, downloads or hardware access."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_thin_lto_object_identity(self):
        target = self.package / "unit.o"
        for magic in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
            target.write_bytes(magic)
            with patch.object(smoke.subprocess, "check_output", return_value=
                              'target triple = "aarch64-unknown-linux-gnu"\n') as check:
                self.assertEqual(smoke.object_identity(target)["format"], "LLVM bitcode")
                self.assertEqual(check.call_args.args[0][0], "llvm-dis")
            for ir in ('target triple = "x86_64-unknown-linux-gnu"\n', "",
                       'target triple = "aarch64-linux"\ntarget triple = "aarch64-linux"\n'):
                with patch.object(smoke.subprocess, "check_output", return_value=ir):
                    with self.assertRaisesRegex(ValueError, "bitcode architecture"):
                        smoke.object_identity(target)

    def test_elf_object_identity(self):
        target = self.package / "unit.o"
        target.write_bytes(b"\x7fELF")
        with patch.object(smoke.subprocess, "check_output", return_value="Machine: AArch64\n"):
            self.assertEqual(smoke.object_identity(target)["machine"], "AArch64")
        for header in ("Machine: X86-64\n", ""):
            with patch.object(smoke.subprocess, "check_output", return_value=header):
                with self.assertRaisesRegex(ValueError, "object architecture"):
                    smoke.object_identity(target)

    def test_unknown_magic_cannot_be_blessed_by_header(self):
        target = self.package / "unit.o"
        target.write_bytes(b"nope")
        with patch.object(smoke.subprocess, "check_output", return_value="Machine: AArch64\n"):
            with self.assertRaisesRegex(ValueError, "object architecture"):
                smoke.object_identity(target)


if __name__ == "__main__":
    unittest.main()
