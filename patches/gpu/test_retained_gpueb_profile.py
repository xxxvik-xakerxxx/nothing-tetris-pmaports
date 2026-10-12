#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Actual pinned producer inputs only; no native build, firmware or MMIO execution."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import audit_gpueb_b41 as b41
import gpueb_firmware as firmware


class RetainedProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lk = b41.signed_lk(b41.read_bounded(cls.args.lk, b41.MAX_LK))
        cls.atf = b41.pinned_atf(b41.read_bounded(cls.args.atf, 900752))
        cls.container = b41.read_bounded(cls.args.gpueb, firmware.MAX_IMAGE)
        cls.snapshot = b41.read_private_snapshot(cls.args.snapshot)
        cls.header = firmware.sections(cls.container)[0].header
        directory = Path(b41.__file__).resolve().parent / "flat-handoff-draft"
        cls.sources = {name: (directory / name).read_bytes() for name in b41.RETAINED_SOURCES}

    def report(self, **changes):
        values = dict(lk=self.lk, atf=self.atf, container=self.container,
                      snapshot=self.snapshot, sources=self.sources)
        values.update(changes)
        return b41.retained_profile(**values)

    def test_actual_signed_primary_is_the_published_flat_image(self):
        report = self.report()
        image = report["retained_image"]
        self.assertEqual(image["bytes"], 156064)
        self.assertEqual(image["source_offset"], 0)
        self.assertEqual(image["sram_offset"], 0)
        self.assertEqual(image["reset_fetch_offset"], 0)
        self.assertEqual(image["initial_jump_target"], 0xac)
        self.assertEqual(report["signed_plaintext_sha256"],
                         "9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7")
        self.assertFalse(report["whole_rv_call_resolution_required_for_image_identity"])

    def test_exact_lk_source_and_retained_source_offsets_are_distinct(self):
        extent = self.report()["selected_member_extent"]
        self.assertEqual(extent["member_payload_offset_from_header"], 512)
        self.assertEqual(extent["lk_destination_offset_from_reservation"], 24)
        self.assertEqual(extent["authentication_pointer_adjustment"], 0)
        self.assertEqual(extent["authentication_and_transform_bytes"], 156064)
        self.assertIn("byte-reader count", extent["loader_success_return"])
        self.assertIn("no upload-span comparison", extent["caller_return_check"])

    def test_stock_span_never_becomes_a_padding_or_start_permission(self):
        report = self.report()
        extent = report["selected_member_extent"]
        self.assertEqual(extent["stock_copy_bytes"], 258744)
        self.assertEqual(extent["uncovered_copy_interval"], [156064, 258744])
        self.assertEqual(extent["uncovered_copy_bytes"], 102680)
        self.assertFalse(report["stock_copy_covered"])
        self.assertFalse(report["execution_permitted"])
        self.assertIn("original count", report["transform_extent"])

    def test_public_b41_container_has_the_same_length_but_distinct_plaintext(self):
        data = b41.read_bounded(self.args.factory, firmware.MAX_IMAGE)
        report = firmware.inspect(data, b41.ROOT_PIN)
        self.assertEqual(report["container_sha256"],
                         "58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22")
        extent = b41.primary_extent(self.lk, firmware.sections(data)[0].header)
        self.assertEqual(extent["member_payload_bytes"], 156064)
        with self.assertRaises(ValueError):
            self.report(container=data)

    def test_changed_snapshot_or_invented_tail_is_rejected(self):
        for snapshot in (self.snapshot[:-1], self.snapshot + bytes(102680),
                         bytes([self.snapshot[0] ^ 1]) + self.snapshot[1:]):
            with self.assertRaises(ValueError):
                self.report(snapshot=snapshot)

    def test_changed_producer_publisher_consumer_or_source_set_is_rejected(self):
        for name in self.sources:
            sources = dict(self.sources)
            sources[name] += b"\n"
            with self.subTest(source=name), self.assertRaises(ValueError):
                self.report(sources=sources)
        with self.assertRaises(ValueError):
            self.report(sources={})

    def test_authentication_precedes_declared_extent_and_snapshot_admission(self):
        container = bytearray(self.container)
        container[4:8] = (258744).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            self.report(container=bytes(container))
        container = bytearray(self.container)
        container[512] ^= 1
        with self.assertRaises(ValueError):
            self.report(container=bytes(container))

    def test_wrong_header_and_binary_identity_are_rejected(self):
        for header in (self.header[:-1], bytes(512),
                       self.header[:4] + (258744).to_bytes(4, "little") + self.header[8:]):
            with self.assertRaises(ValueError):
                b41.primary_extent(self.lk, header)
        with self.assertRaises(ValueError):
            b41.primary_extent(self.lk[:-1], self.header)
        with self.assertRaises(ValueError):
            self.report(atf=self.atf[:-1])

    def test_actual_pointer_count_return_and_caller_semantic_mutants(self):
        for site in (0x1ed8c, 0x1ed90, 0x1ed98, 0x74dc8, 0x75180,
                     0x7518c, 0x75024, 0x75028, 0x7502c, 0x75038,
                     0x7503c, 0x75040, 0x75074, 0x75078, 0x7507c,
                     0x75084, 0x7508c, 0x750f4, 0x7512c, 0x7514c,
                     0x1ee04, 0x1ee08, 0x1ee0c, 0x1ee18):
            changed = bytearray(self.lk)
            changed[site:site + 4] = bytes(4)
            # Bypass identity only; instruction assertions must independently fail.
            with self.subTest(site=hex(site)), patch.object(b41.hashlib, "sha256") as digest:
                digest.return_value.hexdigest.return_value = b41.LK_SHA
                with self.assertRaises(ValueError):
                    b41.primary_extent(bytes(changed), self.header)

    def test_report_contains_only_bounded_identity_and_extent_metadata(self):
        report = self.report()
        self.assertEqual(set(report), {
            "container_sha256", "signed_plaintext_sha256", "lk_payload_sha256",
            "atf_payload_sha256", "retained_source_sha256", "selected_member_extent",
            "retained_image", "transform_extent",
            "whole_rv_call_resolution_required_for_image_identity",
            "stock_copy_covered", "execution_permitted", "remaining_boundary"})
        encoded = json.dumps(report)
        self.assertLess(len(encoded), 8192)
        self.assertNotIn(str(self.args.snapshot), encoded)
        self.assertNotIn("wrapped_material", encoded)

    def test_private_snapshot_symlink_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "alias"
            link.symlink_to(self.args.snapshot)
            with self.assertRaises(OSError):
                b41.read_private_snapshot(link)
            invalid = Path(directory) / "invalid"
            invalid.write_bytes(b"synthetic invalid input")
            invalid.chmod(0o600)
            with self.assertRaises(ValueError):
                b41.read_private_snapshot(invalid)

    def test_cli_strict_extent_gate_returns_two_with_valid_metadata(self):
        args = [sys.executable, "-B", b41.__file__, "--lk", str(self.args.lk),
                "--atf", str(self.args.atf), "--gpueb", str(self.args.gpueb),
                "--snapshot", str(self.args.snapshot), "--require-stock-copy"]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["retained_profile"]["execution_permitted"])
        self.assertFalse(report["retained_profile"]["stock_copy_covered"])
        self.assertIn("no upload/start authorized", result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("lk", "atf", "gpueb", "snapshot", "factory"):
        parser.add_argument("--" + name, type=Path, required=True)
    RetainedProfile.args = parser.parse_args()
    unittest.main(argv=[__file__])
