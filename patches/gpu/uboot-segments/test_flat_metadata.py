#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static source/mutation tests. No native build, git, CI, phone or firmware IO."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

from check_flat_metadata import check_consumer, check_header, check_producer, code
from integrate_flat_metadata import HERE, OWNER, integrate, render_delta, render_patch


class FlatMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HERE / "FLAT-METADATA-PRODUCER.json").read_text())
        cls.header = (HERE / "tetris_gpueb_flat_metadata.h").read_text()
        cls.original = (OWNER / "gpueb-flat-analysis.c").read_text()
        cls.integrated = integrate(cls.original, cls.header)
        tree = Path(os.environ.get("TETRIS_UBOOT_TREE", HERE.parents[3] / "u-boot-mt6878"))
        board = tree / cls.manifest["board_directory"]
        cls.producer = {name: (board / name).read_text() for name in cls.manifest["sources"]}
        spec = importlib.util.spec_from_file_location("existing_ram_admission", OWNER / "test_ram_admission.py")
        cls.ram = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ram)

    def test_actual_producer_and_consumer_contract(self):
        check_header(self.header, self.manifest)
        check_producer(self.producer.__getitem__, self.header, self.manifest)
        check_consumer(self.integrated)

    def test_version_offsets_extent_resource_and_profile_mutants_rejected(self):
        terms = (
            "metadata->handoff_version != TETRIS_FLAT_VERSION",
            "memory->size != TETRIS_FLAT_ARENA_BYTES",
            "memory->base < 0x40000000ULL",
            "memory->base > 0x80000000ULL - TETRIS_FLAT_ARENA_BYTES",
            "(memory->base & (TETRIS_FLAT_ARENA_ALIGN - 1))",
            "metadata->payload_offset || metadata->sram_offset",
            "metadata->authenticated_bytes != TETRIS_FLAT_BYTES",
            "metadata->payload_offset > memory->size",
            "metadata->authenticated_bytes > memory->size - metadata->payload_offset",
            "metadata->sram_offset > TETRIS_FLAT_GPR_OFFSET",
            "metadata->authenticated_bytes > TETRIS_FLAT_GPR_OFFSET - metadata->sram_offset",
            "metadata->profile_id < 1 || metadata->profile_id > 2",
        )
        for term in terms:
            with self.subTest(guard=term), self.assertRaises(ValueError):
                check_header(self.header.replace(term, "0", 1), self.manifest)

    def test_missing_or_relaxed_field_shapes_rejected(self):
        for term in ('of_property_count_strings(node, "compatible") != 1',
                     '!of_device_is_available(node)',
                     'of_property_count_u32_elems(node, name) != 1',
                     '!property || length != 32'):
            with self.subTest(guard=term), self.assertRaises(ValueError):
                check_header(self.header.replace(term, "0", 1), self.manifest)
        for field in ("primary_header", "ciphertext", "leaf_certificate", "container"):
            term = f"!memchr_inv(metadata->{field}_sha256, 0, 32)"
            with self.subTest(provenance=field), self.assertRaises(ValueError):
                check_header(self.header.replace(term, "0", 1), self.manifest)

    def test_profile_id_guard_precedes_array_index(self):
        body = self.ram.function(self.header, "tetris_gpueb_flat_profile_check")
        self.assertLess(body.index("metadata->profile_id > 2"),
                        body.index("profiles[metadata->profile_id - 1]"))
        self.assertIn("return -ENOEXEC;", body)
        altered = self.header.replace("0x96, 0x28", "0x4c, 0xd3", 1)
        with self.assertRaises(ValueError):
            check_header(altered, self.manifest)
        altered = self.header.replace("if (memcmp(metadata->plaintext_sha256,", "if (0 && memcmp(metadata->plaintext_sha256,", 1)
        with self.assertRaises(ValueError):
            check_header(altered, self.manifest)

    def test_actual_producer_profiles_match_ids_not_caller_flags(self):
        producer = self.producer["tetris_gpueb_flat.c"]
        match = re.search(r"profiles\[\]\[32\] = \{(.*?)\};", producer, re.S)
        values = bytes(int(item, 16) for item in re.findall(r"0x([0-9a-f]{2})\b", match[1]))
        expected = b"".join(bytes.fromhex(self.manifest["profiles"][str(i)]) for i in (1, 2))
        self.assertEqual(values, expected)
        for name, value in (("HANDOFF_VERSION", 1), ("PROFILE_PHONE_A", 1), ("PROFILE_B41", 2)):
            self.assertIn(f"#define TETRIS_GPUEB_FLAT_{name} {value}U",
                          self.producer["tetris_gpueb_flat.h"])

    def test_all_ten_actual_metadata_fields_consumed_and_copied(self):
        for field in re.findall(r'READ_(?:U32|DIGEST)\("(nothing,[^"]+)"', self.header):
            changed = self.header.replace('"' + field + '"', '"nothing,invented"', 1)
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_producer(self.producer.__getitem__, changed, self.manifest)
        body = self.ram.function(self.header, "tetris_gpueb_flat_metadata_read")
        self.assertLess(body.index("tetris_gpueb_flat_metadata_validate("), body.index("*result = metadata;"))
        self.assertEqual(body.count("*result ="), 1)
        digest = self.ram.function(self.header, "tetris_gpueb_flat_read_digest")
        self.assertLess(digest.index("length != 32"), digest.index("memcpy(value, property, 32)"))
        self.assertNotRegex(self.header, r"\bconst\s+u8\s*\*\s*\w+\s*;")

    def test_old_producer_without_new_fields_and_drift_rejected(self):
        for name in self.producer:
            changed = dict(self.producer)
            changed[name] += "\n"
            with self.subTest(source=name), self.assertRaises(ValueError):
                check_producer(changed.__getitem__, self.header, self.manifest)
        changed = dict(self.producer)
        changed["tetris_gpueb_flat_publish.c"] = (OWNER / "tetris_gpueb_flat_publish.c").read_text()
        with self.assertRaises(ValueError):
            check_producer(changed.__getitem__, self.header, self.manifest)

    def test_generated_delta_and_shipping_patch_are_concrete_and_deterministic(self):
        delta = render_delta(self.original, self.integrated)
        self.assertEqual(delta, (HERE / "flat-metadata-integration.patch").read_text())
        self.assertEqual(integrate(self.original, self.header), self.integrated)
        shipping = render_patch(self.integrated)
        self.assertEqual(shipping, render_patch(self.integrated))
        source = shipping.split("+++ b/drivers/misc/gpueb-flat-analysis.c\n", 1)[1]
        hunk, *lines = source.splitlines()
        self.assertEqual(hunk, f"@@ -0,0 +1,{len(self.integrated.splitlines())} @@")
        self.assertEqual("\n".join(line[1:] for line in lines) + "\n", self.integrated)

    def test_integration_refuses_changed_or_already_integrated_owner(self):
        for source in (self.original + "\n", self.integrated, ""):
            with self.assertRaises(ValueError):
                integrate(source, self.header)

    def test_existing_resource_and_lifetime_helpers_are_byte_identical(self):
        for name in ("flat_reserved_resource", "flat_plain_reservation", "flat_normal_reserved_ram",
                     "flat_claim_reserved_ram", "flat_read", "flat_bound_probe"):
            self.assertEqual(self.ram.function(self.original, name),
                             self.ram.function(self.integrated, name), name)
        original = self.ram.function(self.original, "flat_probe")
        updated = self.ram.function(self.integrated, "flat_probe")
        self.assertEqual(original.split("erase:", 1)[1], updated.split("erase:", 1)[1])
        self.assertIn(".suppress_bind_attrs = true", self.integrated)
        self.assertNotRegex(code(self.integrated), r"\.remove(?:_new)?\s*=|\.shutdown\s*=")

    def test_existing_ram_ownership_source_gates_on_integrated_candidate(self):
        names = [name for name in unittest.defaultTestLoader.getTestCaseNames(self.ram.RamAdmission)
                 if name not in ("test_read_and_authentication_surface_stays_bounded",
                                 "test_generator_is_deterministic_and_embeds_authoritative_source")]
        suite = unittest.TestSuite(self.ram.RamAdmission(name) for name in names)
        with patch.object(self.ram, "SOURCE", self.integrated):
            result = unittest.TestResult()
            suite.run(result)
        self.assertEqual(result.errors + result.failures, [], result.errors + result.failures)
        self.assertGreaterEqual(result.testsRun, 10)

    def test_digest_and_claim_bypasses_fail_static_gate(self):
        mutations = (
            ("ret = tetris_gpueb_flat_metadata_read(pdev->dev.of_node, memory, &metadata);", "ret = 0;"),
            ("ret = flat_claim_reserved_ram(analysis, memory);", "ret = 0;"),
            ("ret = crypto_shash_digest(desc, analysis->snapshot, size, digest);", "ret = 0;"),
            ("ret = tetris_gpueb_flat_snapshot_check(&metadata, digest, size);", "ret = 0;"),
            ("analysis->metadata = metadata;", ""),
            ("if (ret)\n\t\treturn ret;\n\tsize = metadata.authenticated_bytes;", "size = 156064;"),
            ("kvfree_sensitive(analysis->snapshot, size);", ""),
        )
        for old, new in mutations:
            self.assertEqual(self.integrated.count(old), 1)
            with self.subTest(bypass=old), self.assertRaises(ValueError):
                check_consumer(self.integrated.replace(old, new, 1))

    def test_metadata_helper_has_no_resource_or_activation_operations(self):
        for call in ("enable_irq(1);", "writel(0, 0);", "request_mem_region(0, 1, 0);",
                     "memremap(0, 1, 0);", "arm_smccc_smc(0);", "rproc_boot(0);"):
            with self.subTest(operation=call), self.assertRaises(ValueError):
                check_header(self.header + call, self.manifest)

    def test_cli_renders_without_writing_parent_files(self):
        before = hashlib.sha256((OWNER / "gpueb-flat-analysis.c").read_bytes()).digest()
        for format_name, expected in (("source", self.integrated), ("patch", render_patch(self.integrated)),
                                      ("delta", render_delta(self.original, self.integrated))):
            result = subprocess.run([sys.executable, "-B", str(HERE / "integrate_flat_metadata.py"),
                                     "--format", format_name], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)
        self.assertEqual(hashlib.sha256((OWNER / "gpueb-flat-analysis.c").read_bytes()).digest(), before)


if __name__ == "__main__":
    unittest.main()
