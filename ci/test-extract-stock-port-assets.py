#!/usr/bin/env python3
"""Offline metadata/selection tests; no images, downloads or asset execution."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from elftools.common.exceptions import ELFError

SPEC = importlib.util.spec_from_file_location("stock_assets",
    Path(__file__).with_name("extract-stock-port-assets.py"))
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


def member(name="system.img", size=assets.SYSTEM_IMAGE_SIZE, extra=""):
    return f"Path = {name}\nSize = {size}\nAttributes = A -rw-r--r--\n{extra}\n"


class SelectionTests(unittest.TestCase):
    def test_exact_root_members(self):
        listing = member() + member("vendor.img", 1460764672)
        self.assertEqual(assets.select_image(listing, "system.img"),
                         ("system.img", 1039855616))
        self.assertEqual(assets.select_image(listing, "vendor.img"),
                         ("vendor.img", 1460764672))

    def test_unsafe_ambiguous_and_nonregular(self):
        cases = [member("../system.img"), member("/system.img"), member("dir/system.img"),
                 member("dir\\system.img"), member(extra="Folder = +\n"),
                 member(extra="Symbolic Link = outside\n"),
                 member(extra="Hard Link = vendor.img\n"), member(size=0),
                 member(size=assets.SYSTEM_IMAGE_SIZE + 1), member() + member(), ""]
        for listing in cases:
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                assets.select_image(listing, "system.img")

    def test_filesystem_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "header-fixture"
            for offset, magic, kind in ((1024, b"\xe2\xe1\xf5\xe0", "erofs"),
                                        (1080, b"\x53\xef", "ext4")):
                data = bytearray(1082)
                data[offset:offset + len(magic)] = magic
                image.write_bytes(data)
                self.assertEqual(assets.filesystem(image), kind)
            image.write_bytes(b"not an image")
            with self.assertRaises(ValueError):
                assets.filesystem(image)

    def test_missing_ext4_path_cannot_create_fake_liblog(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            with patch.object(assets.subprocess, "check_output", return_value="") as command, \
                    patch.object(assets.subprocess, "run") as dump:
                with self.assertRaises(ValueError):
                    assets.extract_system_liblog(work / "unused", "ext4", work, work / "output")
                dump.assert_not_called()
                self.assertEqual([call.args[0][2] for call in command.call_args_list],
                    ["stat /system/lib64/liblog.so", "stat /lib64/liblog.so"])
                self.assertFalse((work / "output").exists())

    def test_ext4_symlink_and_oversized_inode_rejected_before_dump(self):
        for text in ("Inode: 3 Type: symlink Size: 10",
                     f"Inode: 3 Type: regular Size: {assets.MAX_LIBLOG + 1}"):
            with tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                with patch.object(assets.subprocess, "check_output", return_value=text), \
                        patch.object(assets.subprocess, "run") as command:
                    with self.assertRaises(ValueError):
                        assets.extract_system_liblog(work / "unused", "ext4", work, work / "out")
                    command.assert_not_called()

    def test_ext4_only_selected_readonly_dump_and_elf_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            def dump(command, **kwargs):
                self.assertEqual(command[0], "debugfs")
                self.assertNotIn("-w", command)
                self.assertEqual(command[2], f"dump /system/lib64/liblog.so {work / 'system-liblog-0'}")
                (work / "system-liblog-0").write_bytes(b"not an ELF")
            with patch.object(assets.subprocess, "check_output", side_effect=[
                    "Inode: 3 Type: regular Size: 10", ""]), \
                    patch.object(assets.subprocess, "run", side_effect=dump) as command:
                # Real ELF validator, not a mocked successful liblog implementation.
                with self.assertRaises(ELFError):
                    assets.extract_system_liblog(work / "unused", "ext4", work, work / "out")
                self.assertEqual(command.call_count, 1)
                self.assertFalse((work / "out").exists())

    def test_ambiguous_system_layout_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            def dump(command, **kwargs):
                target = command[2].split()[-1]
                Path(target).write_bytes(b"selection fixture, not liblog")
            with patch.object(assets.subprocess, "check_output",
                    return_value="Inode: 3 Type: regular Size: 28"), \
                    patch.object(assets.subprocess, "run", side_effect=dump), \
                    patch.object(assets, "audit_liblog") as audit:
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    assets.extract_system_liblog(work / "unused", "ext4", work, work / "out")
                audit.assert_not_called()
                self.assertFalse((work / "out").exists())

    def test_erofs_old_tool_fails_without_full_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            with patch.object(assets.subprocess, "check_output", return_value="--path --ls"), \
                    patch.object(assets.subprocess, "Popen") as command:
                with self.assertRaises(ValueError):
                    assets.extract_system_liblog(work / "unused", "erofs", work, work / "out")
                command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
