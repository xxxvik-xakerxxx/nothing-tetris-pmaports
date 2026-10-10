#!/usr/bin/env python3
"""Offline metadata/selection tests; no images, downloads or asset execution."""
import importlib.util
import hashlib
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile
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


class RuntimeTests(unittest.TestCase):
    def test_five_fixed_paths_no_hwasan_or_debug(self):
        self.assertEqual([row[0] for row in assets.BIONIC_PROVIDERS],
            ["/bin/linker64", "/lib64/bionic/libc.so", "/lib64/bionic/libm.so",
             "/lib64/bionic/libdl.so", "/system/lib64/libc++.so"])
        self.assertEqual(len({row[1] for row in assets.BIONIC_PROVIDERS}), 5)

    def test_pin_rejects_size_hash_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bytes"
            path.write_bytes(b"fixture")
            pin = hashlib.sha256(b"fixture").hexdigest()
            assets.require_pin(path, 7, pin)
            for size, expected in ((8, pin), (7, "0" * 64)):
                with self.assertRaises(ValueError):
                    assets.require_pin(path, size, expected)
            link = path.with_name("symlink")
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                assets.require_pin(link, 7, pin)

    def test_unapproved_path_refused_before_subprocess(self):
        with patch.object(assets.subprocess, "check_output") as command:
            for name in ("/bin/../bin/linker64", "/system/bin/sh", "/lib64/bionic/hwasan/libc.so"):
                with self.assertRaises(ValueError):
                    assets.selected_file(Path("unused"), "ext4", name, Path("unused"), 10, "0" * 64)
            command.assert_not_called()

    def test_readonly_ext4_exact_inode_and_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "selected"
            data = b"non-executable mechanics fixture"
            def dump(command, **kwargs):
                self.assertEqual(command[:3], ["debugfs", "-R", f"dump /bin/linker64 {target}"])
                self.assertNotIn("-w", command)
                self.assertEqual(kwargs["timeout"], 30)
                target.write_bytes(data)
            with patch.object(assets.subprocess, "check_output",
                    return_value=f"Inode: 2 Type: regular Size: {len(data)}"), \
                    patch.object(assets.subprocess, "run", side_effect=dump):
                assets.selected_file(Path("unused"), "ext4", "/bin/linker64", target,
                                     len(data), hashlib.sha256(data).hexdigest())
            self.assertEqual(target.read_bytes(), data)
            with self.assertRaises(ValueError):
                assets.selected_file(Path("unused"), "ext4", "/bin/linker64", target, len(data), "0" * 64)

    def test_ext4_missing_symlink_wrong_size_never_dumped(self):
        for metadata in ("", "Inode: 2 Type: symlink Size: 10", "Inode: 2 Type: regular Size: 11"):
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(assets.subprocess, "check_output", return_value=metadata), \
                    patch.object(assets.subprocess, "run") as dump:
                with self.assertRaises(ValueError):
                    assets.selected_file(Path("unused"), "ext4", "/bin/linker64",
                                         Path(directory) / "selected", 10, "0" * 64)
                dump.assert_not_called()

    def test_erofs_bounded_selection_and_wrong_hash(self):
        for data, result, valid in ((b"fixture", 0, True), (b"too long", 0, False),
                                    (b"fixture", 1, False), (b"invalid", 0, False)):
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "selected"
                from unittest.mock import Mock
                process = Mock(stdout=io.BytesIO(data))
                process.wait.return_value = result
                process.poll.return_value = result
                with patch.object(assets.subprocess, "Popen", return_value=process) as command:
                    arguments = (Path("unused"), "erofs", "/system/lib64/libc++.so", target,
                                 7, hashlib.sha256(b"fixture").hexdigest())
                    if valid:
                        assets.selected_file(*arguments)
                    else:
                        with self.assertRaises(ValueError):
                            assets.selected_file(*arguments)
                    self.assertEqual(command.call_args.args[0][:4],
                        ["timeout", "30", "dump.erofs", "--path=/system/lib64/libc++.so"])

    def test_apex_selected_regular_payload_and_pin(self):
        # Tiny ZIP/ext header fixtures exercise selection, not genuine provider claims.
        data = bytearray(1082)
        data[1080:1082] = b"\x53\xef"
        with tempfile.TemporaryDirectory() as directory:
            apex, target = Path(directory) / "runtime.apex", Path(directory) / "payload"
            with zipfile.ZipFile(apex, "w") as archive:
                archive.writestr("apex_payload.img", data)
                archive.writestr("../unused", b"must never be materialized")
            with patch.object(assets, "RUNTIME_APEX_SIZE", apex.stat().st_size), \
                    patch.object(assets, "RUNTIME_APEX_SHA", assets.digest(apex)), \
                    patch.object(assets, "RUNTIME_PAYLOAD_SIZE", len(data)), \
                    patch.object(assets, "RUNTIME_PAYLOAD_SHA", hashlib.sha256(data).hexdigest()):
                assets.selected_apex_payload(apex, target)
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(set(Path(directory).iterdir()), {apex, target})

    def test_apex_duplicate_unsafe_member_and_wrong_payload_hash(self):
        for case in ("duplicate", "symlink", "wrong-size", "wrong-hash", "nested-only"):
            with tempfile.TemporaryDirectory() as directory:
                apex, target = Path(directory) / "runtime.apex", Path(directory) / "payload"
                with zipfile.ZipFile(apex, "w") as archive:
                    entry = zipfile.ZipInfo("nested/apex_payload.img" if case == "nested-only"
                                            else "apex_payload.img")
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16 if case == "symlink" else 0
                    archive.writestr(entry, b"fixture")
                    if case == "duplicate":
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            archive.writestr("apex_payload.img", b"fixture")
                with patch.object(assets, "RUNTIME_APEX_SIZE", apex.stat().st_size), \
                        patch.object(assets, "RUNTIME_APEX_SHA", assets.digest(apex)), \
                        patch.object(assets, "RUNTIME_PAYLOAD_SIZE", 8 if case == "wrong-size" else 7), \
                        patch.object(assets, "RUNTIME_PAYLOAD_SHA", "0" * 64):
                    with self.assertRaises(ValueError):
                        assets.selected_apex_payload(apex, target)

    def test_system_pin_precedes_all_runtime_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            raw = work / "not-stock"
            raw.write_bytes(b"not pinned system")
            with patch.object(assets, "selected_file") as selected:
                with self.assertRaises(ValueError):
                    assets.extract_bionic_providers(raw, "erofs", work, work / "out")
                selected.assert_not_called()

    def test_provider_routing_and_manifest_without_cached_root(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            raw, out = work / "system.img", work / "artifact"
            def selected(source, kind, name, target, size, expected):
                # Routing fixture only; hashes are separately tested, never promoted here.
                if name.startswith("/system/"):
                    self.assertEqual((source, kind), (raw, "erofs"))
                else:
                    self.assertEqual((source, kind), (work / "runtime-apex-payload.img", "ext4"))
                target.write_bytes(b"routing fixture")
            with patch.object(assets, "require_pin") as pin, \
                    patch.object(assets, "selected_file", side_effect=selected) as selection, \
                    patch.object(assets, "selected_apex_payload") as payload:
                report = assets.extract_bionic_providers(raw, "erofs", work, out)
                pin.assert_called_once_with(raw, assets.SYSTEM_IMAGE_SIZE, assets.SYSTEM_IMAGE_SHA)
                payload.assert_called_once_with(work / "runtime.apex", work / "runtime-apex-payload.img")
                self.assertEqual(selection.call_count, 6)
            self.assertEqual([r["path"] for r in report["providers"]],
                             [r[1] for r in assets.BIONIC_PROVIDERS])
            self.assertEqual([r["sha256"] for r in report["providers"]],
                             [r[3] for r in assets.BIONIC_PROVIDERS])


if __name__ == "__main__":
    unittest.main()
