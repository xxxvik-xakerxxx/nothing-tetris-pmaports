#!/usr/bin/env python3
import runpy
import unittest
from pathlib import Path

scripts = Path(__file__).resolve().parents[1]
check = runpy.run_path(str(scripts / "check-vendor-patch-application.py"))["check"]
source = '''source="
0100-fix.patch.vendor
"
prepare() {
    patch -p1 -d "$_devmods_dir" \\
        < "$srcdir"/0100-fix.patch.vendor
}
'''


class ApplicationTests(unittest.TestCase):
    def test_applied(self):
        check(source)

    def test_missing_application(self):
        with self.assertRaises(ValueError):
            check(source[:source.index("prepare()")] + "prepare() {\n}\n")

    def test_duplicate_application(self):
        with self.assertRaises(ValueError):
            check(source.replace("\n}", '\npatch -p1 -d "$_devmods_dir" '
                                 '< "$srcdir"/0100-fix.patch.vendor\n}'))

    def test_undeclared_application(self):
        with self.assertRaises(ValueError):
            check(source.replace("0100-fix.patch.vendor", "other.patch.vendor", 1))

    def test_comment_is_not_application(self):
        with self.assertRaises(ValueError):
            check(source.replace("    patch", "    # patch"))


if __name__ == "__main__":
    unittest.main()
