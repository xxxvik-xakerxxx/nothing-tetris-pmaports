#!/usr/bin/env python3
"""Balanced GNU-compatible hunks; exact pinned/stacked application, no builds."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import test_lna_metadata_patch as metadata

PATCH = metadata.HERE / "0002-gps-mcudl-query-owned-lna-metadata.patch"
GATE = metadata.HERE / "0003-gps-refuse-unproven-lna-control.patch"


class ContextTests(unittest.TestCase):
    def test_balanced_context_and_counts(self):
        for patch, expected in ((PATCH, 9), (GATE, 1)):
            with self.subTest(patch=patch.name):
                self.check_context(patch, expected)

    def check_context(self, patch, expected):
        lines = patch.read_text().splitlines()
        count = 0
        for i, line in enumerate(lines):
            match = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
            if not match:
                continue
            body = []
            for entry in lines[i + 1:]:
                if entry.startswith(("@@", "diff --git")):
                    break
                self.assertTrue(entry.startswith((" ", "+", "-")), entry)
                body.append(entry)
            old_start, old_count, new_start, new_count = map(int, match.groups())
            self.assertEqual(sum(x[0] in " -" for x in body), old_count)
            self.assertEqual(sum(x[0] in " +" for x in body), new_count)
            if old_count:
                self.assertEqual(len(body) - len(list(drop_context(body))), 3)
                self.assertEqual(len(body) - len(list(drop_context(reversed(body)))), 3)
            else:
                self.assertEqual(old_start, 0)
                self.assertEqual(new_start, 1)
                self.assertTrue(all(x.startswith("+") for x in body))
            count += 1
        self.assertEqual(count, expected)

    def check_application(self, command):
        metadata.MetadataTests.setUpClass()
        changed = re.findall(r"^--- a/(.+)$", PATCH.read_text(), re.M)
        for stacked in (False, True):
            with tempfile.TemporaryDirectory(prefix="gnss-u3-apply-") as directory:
                stack = [metadata.PACKAGE / name for name in metadata.COMPAT_NAMES]
                paths = set(changed)
                if stacked:
                    for patch in stack:
                        paths.update(re.findall(r"^--- a/(.+)$", patch.read_text(), re.M))
                for name in paths:
                    dest = Path(directory) / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(metadata.source(metadata.MODULES, metadata.MODULE_PIN, name).encode())
                if stacked:
                    for patch in stack:
                        if patch.name.startswith("1005-"):
                            clock = Path(directory) / "connectivity/gps/data_link/linux/gps_dl_linux_clock_mng.c"
                            clock.write_bytes(clock.read_bytes().replace(b"\r\n", b"\n"))
                        metadata.apply_patch(directory, patch, allow_offset=True)
                result = subprocess.run(command, cwd=directory, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                expected = metadata.MetadataTests.stacked if stacked else metadata.MetadataTests.fixed
                for name in changed + [metadata.HEADER]:
                    self.assertEqual((Path(directory) / name).read_text(), expected[name])
                gate_command = [str(GATE) if entry == str(PATCH) else entry for entry in command]
                result = subprocess.run(gate_command, cwd=directory, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                from test_lna_control_gate import helper, gated
                fixed = (Path(directory) / metadata.PLAT).read_text()
                self.assertEqual(fixed, gated(expected[metadata.PLAT]))
                self.assertNotIn("pinctrl_select_state", helper(fixed))

    def test_git_apply_exact_output(self):
        self.check_application(["git", "apply", "--whitespace=error", str(PATCH)])

    def test_gnu_patch_fuzz_zero(self):
        candidates = [os.environ.get("TETRIS_GNU_PATCH"), shutil.which("gpatch"), shutil.which("patch")]
        for executable in filter(None, candidates):
            result = subprocess.run([executable, "--version"], text=True, capture_output=True)
            if result.returncode == 0 and "GNU patch" in result.stdout:
                self.check_application([executable, "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)])
                return
        self.skipTest("GNU patch unavailable on host; CI must run this check with GNU patch --fuzz=0")


def drop_context(lines):
    lines = iter(lines)
    for line in lines:
        if not line.startswith(" "):
            yield line
            yield from lines
            break


if __name__ == "__main__":
    unittest.main()
