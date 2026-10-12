#!/usr/bin/env python3
"""Focused LNA source/disassembly checks and mutation rejection; no emulation."""
from pathlib import Path
import os
import sys
import unittest

from evidence import HERE, WINDOWS, load, verify, verify_window, verify_driver_source
from private_evidence import PinnedImage, MNLD_SHA, LIB_SHA


class LnaEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld, cls.lib = load(MNLD, LIB)

    def test_pinned_producer_and_real_consumer(self):
        code = verify(self.mnld, self.lib)
        self.assertEqual(set(code), set(WINDOWS))
        self.assertGreater((0xffff6878 + 0x9a90) & 0xffffffff, 0x22)
        self.assertNotIn(0xffff6878, (0xffff6771, 0xffff6632))
        self.assertEqual(0xde574 - 0xde520, 0x54)
        self.assertEqual(0x712 - 0x6b0, 0x62)
        self.assertLess(0x62, 2 * 0x35)

    def test_whole_hash_mutations_reject_before_decode(self):
        for image, digest in ((self.mnld, MNLD_SHA), (self.lib, LIB_SHA)):
            for offset in (0, len(image.data) // 2, len(image.data) - 1):
                data = bytearray(image.data)
                data[offset] ^= 1
                with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
                    PinnedImage(bytes(data), digest)

    def test_every_instruction_window_byte_mutation_rejects(self):
        images = {"mnld": self.mnld, "lib": self.lib}
        for name, (kind, start, end, _) in WINDOWS.items():
            original = images[kind].read(start, end - start)
            verify_window(name, original)
            for offset in range(len(original)):
                changed = bytearray(original)
                changed[offset] ^= 1
                with self.assertRaisesRegex(ValueError, "changed instruction window"):
                    verify_window(name, changed)
            with self.assertRaises(ValueError):
                verify_window(name, original[:-4])

    def test_matching_source_excludes_case16_and_leaves_output_untouched(self):
        modules = Path(os.environ.get("TETRIS_MODULES_TREE", HERE.parents[3] /
            "android_kernel_modules_nothing_mt6878"))
        source = (modules / "connectivity/gps/gps_mcudl/linux/gps_mcudl_each_device.c").read_bytes()
        proof = verify_driver_source(source)
        self.assertEqual(proof["default_errno"], "EFAULT")
        self.assertFalse(proof["case16_compiled"])
        self.assertFalse(proof["default_copies_output"])
        for old, new in ((b"\tcase GPSDL_IOC_GET_GPS_LNA_PIN:", b"\tcase GPSDL_IOC_QUERY_STATUS:"),
                         (b"\tdefault:\n\t\tretval = -EFAULT;", b"\tdefault:\n\t\tretval = 0;")):
            self.assertIn(old, source)
            with self.assertRaisesRegex(ValueError, "changed inspected mcudl source"):
                verify_driver_source(source.replace(old, new, 1))

    def test_wrapper_requires_specific_receipt_and_retained_output(self):
        source = (HERE.parent / "b41_lna_query_plan.c").read_text()
        self.assertIn("status = query(context, fd, command, &q->lna_pin);", source)
        self.assertIn("result.lna_query_status = status;", source)
        self.assertIn("profile == B41_LNA_PINNED_MCUDL_DISABLED && status == -EFAULT", source)
        self.assertIn("profile == B41_LNA_PINNED_METADATA_ABSENT && status == -ENODATA", source)
        self.assertIn("q->lna_pin == 0", source)
        self.assertIn("result.missing_inputs &= ~B41_FIRST_LNA_QUERY;", source)
        self.assertIn("snapshot->first_config_lna_word || q->lna_pin || (q->present & B41_FIRST_LNA_QUERY)", source)

    def test_existing_consumers_preserve_wrapper_output(self):
        runtime = (HERE.parent / "b41_runtime_config.c").read_text()
        bundle = (HERE.parent / "b41_startup_bundle.c").read_text()
        native = (HERE.parent / "b41_native_arguments.c").read_text()
        self.assertIn("result.first = *base;", runtime)
        self.assertIn("result.first.provenance[i] == B41_FIRST_UNKNOWN", runtime)
        self.assertIn("b41_runtime_config_apply(first, runtime, xml, xml_size, &result.runtime)", bundle)
        self.assertIn("memcpy(result.abi.first, result.runtime.first.bytes, B41_FIRST_CONFIG_SIZE);", bundle)
        self.assertIn("b->runtime.first.missing_inputs || b->runtime.first.unresolved_bytes", native)
        self.assertIn("if (!b->runtime.first.provenance[i])", native)
        for text in (runtime, bundle, native):
            self.assertNotIn("B41_FIRST_LNA_QUERY", text)
            self.assertNotIn("B41_FIRST_LNA_RESULT", text)
        self.assertIn("missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;", native)
        self.assertIn("b->runtime.first.xml_policy_missing", native)

    def test_native_helper_stays_ci_only_and_tests_actual_consumers(self):
        runner = (HERE / "run_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertLess(runner.index('"${CI:-}"'), runner.index('"${CC:-cc}"'))
        self.assertIn("-fsanitize=address,undefined", runner)
        for name in ("b41_lna_query_plan.c", "b41_runtime_config.c", "b41_startup_bundle.c",
                     "b41_native_arguments.c", "test_integration.c"):
            self.assertIn(name, runner)
        fixture = (HERE / "test_integration.c").read_text()
        for call in ("b41_queries_collect_with_lna_plan", "b41_first_config_from_lna_plan",
                     "b41_runtime_config_apply", "b41_startup_bundle_build",
                     "b41_native_arguments_config_missing"):
            self.assertIn(call, fixture)
        for forbidden in ("dlopen(", "b41_native_arguments_prepare(",
                          "b41_native_arguments_execute(", "ioctl("):
            self.assertNotIn(forbidden, fixture)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_static.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
