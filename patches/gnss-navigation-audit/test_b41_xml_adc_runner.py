#!/usr/bin/env python3
"""Runner rejection/syntax checks only: never compile or execute ELF code."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_xml_adc_ci.sh"


class RunnerTests(unittest.TestCase):
    def reject(self, args, message, ci="true", script=RUNNER):
        env = dict(os.environ, CI=ci, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(["sh", str(script), *args], env=env, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(message, result.stderr)

    def test_ci_guard_before_any_inputs_or_tools(self):
        self.reject([], "CI-only", ci="false")
        self.reject([], "CI-only", ci="")

    def test_argument_count(self):
        self.reject([], "usage:")

    def test_unknown_mode(self):
        self.reject(["load", "/lib", "/xml", "/mnld", "/out"], "Unknown build mode")

    def test_relative_inputs(self):
        for index in range(1, 5):
            args = ["all", "/lib", "/xml", "/mnld", "/out"]
            args[index] = "relative"
            self.reject(args, "absolute input/output paths")

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as output:
            marker = Path(output) / "retained"
            marker.write_bytes(b"unchanged")
            self.reject(["all", "/lib", "/xml", "/mnld", output], "must be new")
            self.assertEqual(marker.read_bytes(), b"unchanged")

    def test_old_runners_ci_guard(self):
        for name in ("run_xml_globals_ci.sh", "run_slot0_adc_ci.sh"):
            self.reject([], "CI-only", ci="false", script=HERE / name)

    def test_shell_syntax(self):
        for name in ("run_xml_adc_ci.sh", "run_xml_globals_ci.sh", "run_slot0_adc_ci.sh"):
            subprocess.run(["sh", "-n", str(HERE / name)], check=True, timeout=5)

    def test_dependency_and_build_contract(self):
        source = RUNNER.read_text()
        for name in ("b41_xml_config.c", "b41_xml_config.h", "b41_xml_globals.c",
                     "b41_xml_globals.h", "b41_slot0_adc.c", "b41_slot0_adc.h",
                     "test_b41_xml_globals.c", "test_b41_slot0_adc.c",
                     "test_b41_xml_adc_static.py", "run_xml_globals_ci.sh", "run_slot0_adc_ci.sh"):
            self.assertTrue((HERE / name).is_file(), name)
            self.assertIn(name, source)
        self.assertIn("B41_BIONIC_DEPS", source)
        self.assertIn("aarch64-linux-android28-clang", source)
        self.assertIn("-Wl,--no-undefined", source)
        self.assertIn("-pthread", source)
        self.assertLess(source.index('"$python"'), source.index('"$compiler" -std=c11'))
        self.assertIn("bionic=api28-build-only-if-selected", source)
        for forbidden in ("qemu-", "adb ", "fastboot ", "dlopen(", "-DNDEBUG"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
