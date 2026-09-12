#!/usr/bin/env python3
"""Tests for inventory semantics, not modem execution."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "symbol_audit", Path(__file__).with_name("audit-object-symbols.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SymbolAuditTest(unittest.TestCase):
    def inspect(self, *outputs):
        paths = [Path(f"part{i}.o") for i in range(len(outputs))]
        with patch.object(audit.subprocess, "check_output", side_effect=outputs), \
                patch.object(audit, "digest", return_value="test-only"):
            return audit.audit(paths, "nm")

    def test_cross_object_resolution(self):
        result = self.inspect("provider U 0 0\nkernel U 0 0\n", "provider T 0 8\n")
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(list(result["unresolved"]), ["kernel"])
        self.assertIn("provider", result["resolved_within_set"])
        self.assertFalse(result["module_export_and_crc_compatibility_verified"])

    def test_undefined_weak_is_not_a_provider(self):
        result = self.inspect("optional w 0 0\n", "optional U 0 0\n")
        self.assertIn("optional", result["unresolved"])
        self.assertIn("optional", result["unresolved_weak"])

    def test_defined_weak_is_a_provider(self):
        result = self.inspect("helper U 0 0\n", "helper W 0 8\n")
        self.assertEqual(result["unresolved_count"], 0)
        self.assertEqual(result["resolved_within_set"]["helper"]["providers"][0]["kind"], "W")

    def test_multiple_providers_remain_visible(self):
        result = self.inspect("same T 0 8\n", "same T 0 8\n")
        self.assertEqual(len(result["multiple_definitions"]["same"]), 2)

    def test_invalid_nm_output_fails(self):
        with self.assertRaises(ValueError):
            list(audit.parse_symbols("unexpected output"))
        with self.assertRaises(ValueError):
            self.inspect("mystery ? 0 0\n")


if __name__ == "__main__":
    unittest.main()
