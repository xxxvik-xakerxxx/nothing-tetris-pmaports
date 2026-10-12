#!/usr/bin/env python3
"""Source-only checks. These do not compile or execute the decoder."""
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from pinned_helpers import HERE, function, shared_policies, sources

UBOOT = Path(os.environ.get("TETRIS_BOOT_EVIDENCE_UBOOT", HERE.parents[4] / "u-boot-mt6878"))


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = sources(UBOOT)
        cls.decoder = (HERE / "boot_evidence.c").read_text()
        cls.header = (HERE / "boot_evidence.h").read_text()
        cls.fixture = (HERE / "test_boot_evidence.c").read_text()

    def test_policy_is_derived_from_pinned_source(self):
        table = re.search(r'expected_policy\[2\]\[8\]\s*=\s*\{(.*?)\n\s*\};',
                          self.decoder, re.S)[1]
        words = [[int(x.strip().removesuffix("ULL"), 0) for x in row.split(",") if x.strip()]
                 for row in re.findall(r'\{([^{}]*)\}', table)]
        self.assertEqual(words, shared_policies(self.src["tetris_modem_emi.c"]))
        self.assertNotEqual(words[0], words[1])

    def test_profile_digest_matches_actual_policy_helper(self):
        body = function(self.src["tetris_modem_emi.c"], "tetris_modem_plan_emi_policy")
        for source in (body, self.decoder, self.fixture):
            digest = re.search(r'digest\[32\]\s*=\s*(.*?);', source, re.S)[1]
            self.assertEqual("".join(re.findall(r'\\x([0-9a-f]{2})', digest)),
                             "5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f")

    def test_current_helper_bodies_match_the_pin(self):
        for filename, name in (("tetris_modem_layout.c", "tetris_modem_plan_emi"),
                               ("tetris_modem_emi.c", "tetris_modem_plan_emi_policy")):
            current = (UBOOT / "board/mediatek/mt6878" / filename).read_text()
            self.assertEqual(function(current, name), function(self.src[filename], name),
                             "planner changed: review and repin before claiming current-source parity")

    def test_endpoint_convention_and_marker_scope(self):
        helper = function(self.src["tetris_modem_layout.c"], "tetris_modem_plan_emi")
        self.assertIn("size >= limit - start", helper)
        self.assertIn("out.start_readback = start;", helper)
        self.assertIn("out.end_readback = (start + size) | (1ULL << 43);", helper)
        self.assertIn("(1ULL << 43)", self.src["tetris_modem_emi.h"])
        self.assertEqual(self.decoder.count("~TETRIS_SMEM_BOOT_END_MARKER"), 1)
        self.assertIn("(r->actual_end & ~TETRIS_SMEM_BOOT_END_MARKER) != end", self.decoder)
        self.assertIn("r->actual_start != r->range_start", self.decoder)
        self.assertIn("r->actual_enable != 1", self.decoder)
        self.assertIn("r->policy[group] != expected_policy[bank][group]", self.decoder)
        for rule in ("origin = 0x40000000ULL", "limit = origin + (1ULL << 35)",
                     "r->range_size >= limit - r->range_start", "& 4095"):
            self.assertIn(rule, self.decoder)

    def test_exact_header_and_order(self):
        for rule in ("result.version != 1", "result.bytes != TETRIS_SMEM_BOOT_BYTES",
                     "result.scope != 1", "result.count != 2", "result.ap != 6878",
                     "result.md != 6299", "result.loaded_stage != 11", "result.boot_stage != 15",
                     "result.errors[0] || result.errors[1] || result.errors[2] || result.reserved",
                     "memcmp(result.preloader_sha256, digest, 32)", "r->bank != bank",
                     "r->slot != 42 + bank"):
            self.assertIn(rule, self.decoder)
        self.assertIn('"nothing,modem-smem-boot-evidence"', self.header)
        self.assertIn("TETRIS_SMEM_BOOT_BYTES 336U", self.header)

    def test_atomic_disjoint_bounded_snapshot(self):
        self.assertEqual(self.decoder.count("memcpy(output,"), 1)
        self.assertTrue(self.decoder.rstrip().endswith("memcpy(output, &result, sizeof(result));\n\treturn 0;\n}"))
        copy = self.decoder.index("memcpy(&snapshot, banks")
        for guard in ("wire_bytes != TETRIS_SMEM_BOOT_BYTES", "banks_bytes != sizeof(snapshot)",
                      "output_bytes < sizeof(result)", "overlaps(wire, wire_bytes, banks, banks_bytes)",
                      "overlaps(wire, wire_bytes, output, output_bytes)",
                      "overlaps(banks, banks_bytes, output, output_bytes)",
                      "!span(wire, wire_bytes)", "!span(banks, banks_bytes)", "!span(output, output_bytes)"):
            self.assertLess(self.decoder.index(guard), copy)
        self.assertIn("(size_t)p <= (size_t)-1 - bytes", self.decoder)
        self.assertIn("w->base <= ~0ULL - w->capacity", self.decoder)
        self.assertIn("r->range_start > ~0ULL - r->range_size", self.decoder)
        for rule in ("r->reservation_base != w->base", "r->reservation_capacity != w->capacity",
                     "r->range_start != w->base", "r->range_size > w->capacity"):
            self.assertIn(rule, self.decoder)

    def test_pure_copied_evidence_only(self):
        for call in ("malloc", "kmalloc", "ioremap", "writel", "arm_smccc_smc", "fdt_setprop",
                     "tetris_smem_create", "tetris_smem_preview"):
            self.assertNotRegex(self.decoder, r'\b' + call + r'\s*\(')
        structs = self.header[self.header.index("struct tetris_smem_boot_record {"):
                              self.header.index("/* Pure v1 decoder")]
        structs = re.sub(r'/\*.*?\*/', "", structs, flags=re.S)
        self.assertNotIn("*", structs)
        self.assertNotRegex(structs, r'\b(admitted|ready|grant|permission|owner)\b')
        for total in ("1204224", "39190528"):
            self.assertNotIn(total, self.decoder)

    def test_ci_fixture_uses_real_bodies_and_fault_groups(self):
        runner = (HERE / "check.py").read_text()
        gate = runner.index('if os.environ.get("CI") != "true"')
        self.assertLess(gate, runner.index('os.environ.get("CC", "cc")'))
        for required in ("-fsanitize=address,undefined", 'HERE / "boot_evidence.c"',
                         "oracle_c(src)", '"--native-ci"', 'os.environ.get("GITHUB_ACTIONS") != "true"',
                         'HERE / "test_roundtrip.c"', 'tetris_modem_smem_evidence.c'):
            self.assertIn(required, runner)
        for required in ("every_field_and_policy_bit", "absent_truncated_alias_overflow",
                         "reservation_and_range_faults", "UINTPTR_MAX", "SIZE_MAX",
                         "byte < 336", "bit < 8", "sizeof(*banks)", "NULL",
                         "banks.nc.base +=", "memcmp(&before, &output", "memcmp(arena, saved",
                         "endpoint_boundaries_and_physical_order", "end - 1", "(1ULL << 44)"):
            self.assertIn(required, self.fixture)

    def test_producer_wire_offsets_read_only(self):
        producer = (UBOOT / "board/mediatek/mt6878/tetris_modem_smem_evidence.c").read_text()
        for offset, value in ((4, "sizeof(encoded)"), (8, "TETRIS_MODEM_SMEM_EVIDENCE_SCOPE_BL33"),
                              (12, "2"), (16, "6878"), (20, "6299")):
            self.assertIn(f"encode32(encoded + {offset}, {value});", producer)
        for offset in (8, 16, 24, 32, 40, 48, 56):
            self.assertIn(f"encode64(record + {offset},", producer)
        self.assertIn("memcpy(encoded + 48, bootstrap->preloader_sha256, 32)", producer)
        self.assertIn("encode64(record + 64 + group * 8,", producer)

    def test_extraction_bounds_ignore_literal_and_comment_braces(self):
        sample = 'int helper(void) { /* } */ const char *s = "}"; if (s) { return 1; } }\nint other(void) {}'
        self.assertEqual(function(sample, "helper"), sample[:sample.index("\n")])
        with self.assertRaises(ValueError):
            function("int helper(void) { /* } */", "helper")

    def test_unknown_source_rejected_before_extraction(self):
        with patch("pinned_helpers.subprocess.check_output", return_value=b"unknown revision"):
            with self.assertRaisesRegex(ValueError, "pinned source mismatch"):
                sources(UBOOT)


if __name__ == "__main__":
    unittest.main()
