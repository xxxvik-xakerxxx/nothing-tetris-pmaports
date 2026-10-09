#!/usr/bin/env python3
"""Mock every native CLI: no local mkimage/debugfs/dtc execution."""
import argparse
import contextlib
import io
import hashlib
import os
from pathlib import Path
import shlex
import struct
import tempfile
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

import build_diagnostic_boot as builder
import test_diagnostic_dt as dt_test


def fit_tree():
    tree = {"/": {"description": b"Native FIT\0", "#address-cells": struct.pack(">I", 1)},
            "/images": {}, "/configurations": {"default": b"native-display\0"},
            "/configurations/native-display": {"description": b"Native display\0", "kernel": b"kernel\0",
                                                  "fdt": b"fdt\0", "ramdisk": b"initrd\0"}}
    for name, kind, compression, address in (
        ("kernel", "kernel", "gzip", 0x42000000),
        ("fdt", "flat_dt", "none", 0x47000000),
        ("initrd", "ramdisk", "none", 0x45500000),
    ):
        node = {"description": name.encode() + b"\0", "data": b"payload", "type": kind.encode() + b"\0",
                "arch": b"arm64\0", "compression": compression.encode() + b"\0",
                "load": struct.pack(">I", address), "entry": struct.pack(">I", address)}
        if name != "fdt":
            node["os"] = b"linux\0"
        tree["/images/" + name] = node
    return tree


class FakeTools:
    def __init__(self, args):
        self.args = args
        self.metadata = fit_tree()
        self.order = list(builder.IMAGES)
        self.calls = []
        self.fs = {"boot_image.itb": args.normal_fit.read_bytes(), "other.txt": b"unchanged"}
        self.kernel = b"\x1f\x8bimmutable kernel"
        self.initrd = b"immutable initramfs"
        self.change_kernel = False
        self.change_initrd = False
        self.change_other = False
        self.fsck_failure = False

    def __call__(self, args, cwd=None):
        args = list(map(str, args))
        self.calls.append(args)
        command = args[0]
        if command == "fdtget":
            if args[1] == "-l":
                node = args[3]
                children = {"/": ["images", "configurations"], "/images": self.order,
                            "/configurations": ["native-display"]}.get(node, [])
                return "\n".join(children) + ("\n" if children else "")
            if args[1] == "-p":
                keys = list(self.metadata[args[3]])
                return "\n".join(keys) + ("\n" if keys else "")
            return " ".join(format(byte, "x") for byte in self.metadata[args[4]][args[5]]) + "\n"
        if command == "dumpimage":
            index = int(args[args.index("-p") + 1])
            diagnostic = Path(args[-1]).name == builder.artifact_names(self.args.mode)[0]
            values = [self.kernel + (b"changed" if self.change_kernel and diagnostic else b""),
                      self.args.diagnostic_dtb.read_bytes() if diagnostic else self.args.normal_dtb.read_bytes(),
                      self.initrd + (b"changed" if self.change_initrd and diagnostic else b"")]
            Path(args[args.index("-o") + 1]).write_bytes(values[index])
            return "mock extraction\n"
        if command == "mkimage":
            Path(args[-1]).write_bytes(b"DIAGNOSTIC FIT")
            return "mock mkimage\n"
        if command == "e2fsck":
            if self.fsck_failure:
                raise RuntimeError("mock e2fsck failure")
            assert "-n" in args and "-y" not in args
            return "mock clean filesystem\n"
        if command == "debugfs":
            request = shlex.split(args[args.index("-R") + 1])
            if request[0] == "rdump":
                directory = Path(request[2])
                for name, value in self.fs.items():
                    (directory / name).write_bytes(value)
            elif request[0] == "ls":
                return "/12/100644/0/0/boot_image.itb/10/\n"
            elif request[0] == "rm":
                del self.fs["boot_image.itb"]
            elif request[0] == "write":
                self.fs["boot_image.itb"] = Path(request[1]).read_bytes()
                if self.change_other:
                    self.fs["other.txt"] = b"wrong"
            elif request[0] != "set_inode_field":
                raise AssertionError(args)
            return ""
        raise AssertionError(args)


class DiagnosticBuilder(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gpu-builder-mock-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.args = argparse.Namespace(normal_fit=root / "normal.itb", boot_image=root / "boot.img",
                                       normal_dtb=root / "normal.dtb", diagnostic_dtb=root / "diagnostic.dtb",
                                       its=root / "boot_image.its", output_dir=root / "diagnostic-out",
                                       require_boot_image=False, mode="vgpu-observe", baseline_dtb=None)
        for name in ("normal_fit", "normal_dtb", "diagnostic_dtb", "its"):
            getattr(self.args, name).write_bytes(name.encode())
        header = bytearray(4096)
        header[1080:1082] = b"\x53\xef"
        struct.pack_into("<II", header, 1116, 0x38, 2)
        self.args.boot_image.write_bytes(header)
        dt = dt_test.DiagnosticDelta()
        dt.setUp()
        self.normal_tree, self.diagnostic_tree = dt.normal, dt.diagnostic
        self.environment = patch.dict(os.environ, {"CI": "true"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.read_tree = patch.object(builder, "read_tree", side_effect=lambda path:
                                      self.normal_tree if path == self.args.normal_dtb.resolve() else self.diagnostic_tree)
        self.read_tree.start()
        self.addCleanup(self.read_tree.stop)
        self.tools = FakeTools(self.args)

    def test_full_build_preserves_inputs_and_payloads(self):
        before = {name: builder.sha256(getattr(self.args, name)) for name in
                  ("normal_fit", "boot_image", "normal_dtb", "diagnostic_dtb", "its")}
        result = builder.build(self.args, self.tools)
        self.assertEqual(result["boot_filesystem"], "ext2")
        self.assertIsNone(result["packaging_gate"])
        self.assertEqual(set(result["artifacts"]), {builder.FIT_NAME, builder.BOOT_NAME})
        for name, digest in before.items():
            self.assertEqual(builder.sha256(getattr(self.args, name)), digest)
        self.assertEqual(result["immutable_kernel_sha256"], hashlib.sha256(self.tools.kernel).hexdigest())
        self.assertEqual(result["immutable_initramfs_sha256"], hashlib.sha256(self.tools.initrd).hexdigest())
        fsck = [call for call in self.tools.calls if call[0] == "e2fsck"]
        self.assertEqual(len(fsck), 2)
        self.assertTrue(all("-n" in call for call in fsck))
        self.assertFalse(any(call[0] in ("mount", "umount", "dd") for call in self.tools.calls))

    def test_unknown_format_fit_only(self):
        self.args.boot_image.write_bytes(b"unknown format")
        result = builder.build(self.args, self.tools)
        self.assertEqual(set(result["artifacts"]), {builder.FIT_NAME})
        self.assertIsNotNone(result["packaging_gate"])
        self.assertFalse(any(call[0] == "debugfs" for call in self.tools.calls))

    def test_unknown_format_strict_gate(self):
        self.args.boot_image.write_bytes(b"unknown format")
        self.args.require_boot_image = True
        with self.assertRaisesRegex(ValueError, "Unknown boot filesystem"):
            builder.build(self.args, self.tools)

    def test_wrong_fit_order_rejected(self):
        self.tools.order.reverse()
        with self.assertRaisesRegex(ValueError, "child order"):
            builder.build(self.args, self.tools)

    def test_external_fit_payload_rejected(self):
        self.tools.metadata["/images/kernel"]["data-offset"] = b"\0\0\0\x04"
        with self.assertRaisesRegex(ValueError, "inline FIT"):
            builder.build(self.args, self.tools)

    def test_load_address_change_rejected(self):
        self.tools.metadata["/images/initrd"]["load"] = struct.pack(">I", 0x40000000)
        with self.assertRaisesRegex(ValueError, "load/entry"):
            builder.build(self.args, self.tools)

    def test_kernel_mutation_rejected(self):
        self.tools.change_kernel = True
        with self.assertRaisesRegex(ValueError, "immutable kernel"):
            builder.build(self.args, self.tools)

    def test_initramfs_mutation_rejected(self):
        self.tools.change_initrd = True
        with self.assertRaisesRegex(ValueError, "immutable kernel/initramfs"):
            builder.build(self.args, self.tools)

    def test_embedded_normal_fit_mismatch_rejected_before_writes(self):
        self.tools.fs["boot_image.itb"] = b"different normal FIT"
        with self.assertRaisesRegex(ValueError, "differs from input FIT"):
            builder.build(self.args, self.tools)
        self.assertFalse(any(call[:2] == ["debugfs", "-w"] for call in self.tools.calls))

    def test_other_boot_file_mutation_rejected(self):
        self.tools.change_other = True
        with self.assertRaisesRegex(ValueError, "Other boot filesystem"):
            builder.build(self.args, self.tools)

    def test_existing_output_rejected(self):
        self.args.output_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "must be new"):
            builder.build(self.args, self.tools)

    def test_ci_only(self):
        with patch.dict(os.environ, {"CI": "false"}):
            with self.assertRaisesRegex(ValueError, "CI-only"):
                builder.build(self.args, self.tools)

    def test_fsck_failure_stops_before_writes(self):
        self.tools.fsck_failure = True
        with self.assertRaisesRegex(RuntimeError, "e2fsck"):
            builder.build(self.args, self.tools)
        self.assertFalse(any(call[:2] == ["debugfs", "-w"] for call in self.tools.calls))

    def test_structured_cli(self):
        argv = ["build_diagnostic_boot.py"]
        for name in ("normal_fit", "boot_image", "normal_dtb", "diagnostic_dtb", "its", "output_dir"):
            argv += ["--" + name.replace("_", "-"), str(getattr(self.args, name))]
        argv.append("--require-boot-image")
        with patch("sys.argv", argv), patch.object(builder, "build", return_value={"diagnostic_only": True}) as mocked:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                builder.main()
        self.assertTrue(mocked.call_args.args[0].require_boot_image)
        self.assertIn('"diagnostic_only": true', output.getvalue())

    def test_known_ext_family_and_partition_rejection(self):
        self.assertEqual(builder.ext_format(self.args.boot_image), "ext2")
        data = bytearray(self.args.boot_image.read_bytes())
        struct.pack_into("<I", data, 1116, 4)
        self.args.boot_image.write_bytes(data)
        self.assertEqual(builder.ext_format(self.args.boot_image), "ext3")
        struct.pack_into("<I", data, 1120, 0x40)
        self.args.boot_image.write_bytes(data)
        self.assertEqual(builder.ext_format(self.args.boot_image), "ext4")
        data[510:512] = b"\x55\xaa"
        self.args.boot_image.write_bytes(data)
        self.assertIsNone(builder.ext_format(self.args.boot_image))

    def test_modem_three_dt_chain_and_names(self):
        self.args.mode = "modem-preflight"
        self.args.baseline_dtb = self.args.normal_dtb.parent / "modem-off.dtb"
        self.args.baseline_dtb.write_bytes(b"verified modem off baseline")
        baseline = {"OFF": {}}
        checker = SimpleNamespace(check_native_baseline=Mock(), validate_trees=Mock(return_value="/spm/md-observer"))
        events = []
        checker.check_native_baseline.side_effect = lambda *args: events.append("normal-to-OFF")
        checker.validate_trees.side_effect = lambda *args: events.append("OFF-to-active") or "/spm/md-observer"
        def trees(path):
            if path == self.args.baseline_dtb.resolve():
                return baseline
            return self.normal_tree if path == self.args.normal_dtb.resolve() else self.diagnostic_tree
        with patch.object(builder, "load_modem_checker", return_value=checker), patch.object(builder, "read_tree", side_effect=trees):
            result = builder.build(self.args, self.tools)
        checker.check_native_baseline.assert_called_once_with(self.normal_tree, baseline)
        checker.validate_trees.assert_called_once_with(baseline, self.diagnostic_tree)
        self.assertEqual(events, ["normal-to-OFF", "OFF-to-active"])
        self.assertEqual(result["mode"], "modem-preflight")
        self.assertEqual(result["dt_validation"], "normal-to-OFF-to-active")
        self.assertEqual(set(result["artifacts"]), set(builder.artifact_names("modem-preflight")))
        self.assertIn("baseline_dtb", result["inputs"])
        self.assertFalse(any("vgpu-observe-diagnostic" in name for name in result["artifacts"]))

    def test_modem_missing_baseline_export_fails_closed(self):
        checker = SimpleNamespace(validate_trees=Mock())
        with patch.object(builder, "load_modem_checker", return_value=checker):
            with self.assertRaisesRegex(ValueError, "export is not ready"):
                builder.validate_mode("modem-preflight", self.args.normal_dtb,
                                      self.args.diagnostic_dtb, self.args.normal_dtb)
        checker.validate_trees.assert_not_called()

    def test_modem_failed_off_gate_does_not_activate(self):
        checker = SimpleNamespace(check_native_baseline=Mock(side_effect=ValueError("Unapproved normal-to-OFF delta")),
                                  validate_trees=Mock())
        with patch.object(builder, "load_modem_checker", return_value=checker):
            with self.assertRaisesRegex(ValueError, "Unapproved"):
                builder.validate_mode("modem-preflight", self.args.normal_dtb,
                                      self.args.diagnostic_dtb, self.args.normal_dtb)
        checker.validate_trees.assert_not_called()

    def test_gpu_baseline_option_rejected(self):
        with self.assertRaisesRegex(ValueError, "only for modem-preflight"):
            builder.validate_mode("vgpu-observe", self.args.normal_dtb,
                                  self.args.diagnostic_dtb, self.args.normal_dtb)


if __name__ == "__main__":
    unittest.main()
