#!/usr/bin/env python3
"""Structural and exact stacked-application checks; no native compilation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import generate as g


def digest(data):
    return hashlib.sha512(data).hexdigest()


class WriteBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = g.stacked()
        cls.fixed = {p: g.transform(p, cls.old[p]) for p in g.SOURCES}

    def body(self, path, name, fixed=True):
        text = (self.fixed if fixed else self.old)[path]
        return g.function_span(text, name).text(text)

    def test_01_deterministic_patch_and_stack_identity(self):
        manifest = json.loads((g.HERE / "STAGING.json").read_text())
        self.assertEqual(manifest["connectivity_commit"], g.PIN)
        self.assertEqual(manifest["patch_sha512"], digest(g.PATCH.read_bytes()))
        self.assertEqual(manifest["prerequisite_sha512"],
                         {p.name: digest(p.read_bytes()) for p in g.stack()})
        self.assertEqual(manifest["stacked_source_sha512"],
                         {p: digest(t.encode()) for p, t in self.old.items()})
        self.assertEqual(g.PATCH.read_text(), g.generate(baseline=self.old))
        self.assertEqual(g.generate(baseline=self.old), g.generate(baseline=self.old))
        apkbuild = (g.PACKAGE / "APKBUILD").read_text()
        self.assertIn('_connmods_commit="' + g.PIN + '"', apkbuild)
        for patch in g.stack():
            self.assertIn(patch.name, apkbuild)

    def test_02_zero_device_precedes_all_access_and_count_is_bounded(self):
        body = self.body(g.DEVICE, "gps_each_device_write")
        zero = body.index(g.ZERO_DEVICE)
        self.assertLess(zero, body.index("filp->private_data"))
        self.assertLess(zero, body.index("current->pid"))
        bound = body.index(g.BOUND)
        for operation in ("gps_each_link_rec_write(", "copy_size = count;", "copy_from_user("):
            self.assertLess(bound, body.index(operation))
        self.assertNotIn("copy_size = GPS_DATA_PATH_BUF_MAX", body)
        self.assertIn("copy_from_user(&dev->o_buf[0], &buf[0], copy_size)", body)
        self.assertIn("copy_size, true, true);", body)
        self.assertIn("filp->f_flags & O_NONBLOCK", body)
        self.assertIn("else\n\t\t\t\tretval = gps_each_link_write(", body)
        self.assertIn("retlen = copy_size;", body)
        self.assertIn("retlen = -EFAULT;", body)

    def test_03_capacity_guard_precedes_wait_in_both_configurations(self):
        body = self.body(g.LINK, g.HELPER)
        start = body.index("} else if (gdl_ret == GDL_FAIL_NOSPACE")
        guard = body.index(g.UNAVAILABLE, start)
        self.assertLess(body.index("gdl_dma_buf_put("), guard)
        self.assertIn("gdl_ret == GDL_FAIL_BUSY", body[start:guard])
        self.assertIn("gdl_ret == GDL_FAIL_NOENTRY", body[start:guard])
        for operation in ("gps_dma_buf_show(", "gps_dl_link_wait_on("):
            self.assertLess(guard, body.index(operation, start))
        self.assertEqual(body.count("gdl_dma_buf_put("), 1)

    def test_04_queue_guard_precedes_poll_completion(self):
        body = self.body(g.LINK, g.HELPER)
        event = body.index("gps_dl_link_event_send(GPS_DL_EVT_LINK_WRITE")
        guard = body.index(g.QUEUED)
        self.assertLess(event, guard)
        self.assertLess(guard, body.index("#if (GPS_DL_NO_USE_IRQ == 1)"))
        self.assertLess(guard, body.index("gps_dl_hal_a2d_tx_dma_wait_until_done_and_stop_it("))
        self.assertIn("if (wait_tx_done) {", body)
        self.assertIn("while (!gps_dma_buf_is_empty(&p->tx_dma_buf));", body)
        self.assertIn("if (nonblocking && !len)", body)
        self.assertLess(body.index(g.ZERO_LINK), body.index("gps_dl_link_get("))

    def test_05_legacy_wrapper_preserves_wait_tx_done(self):
        self.assertEqual(self.body(g.LINK, "gps_each_link_write_with_opt") + "\n\n", g.WRAPPER)
        self.assertEqual(self.body(g.LINK, "gps_each_link_write"),
                         self.body(g.LINK, "gps_each_link_write", fixed=False))
        # Remove only added options and recover the complete old TX implementation.
        new = self.body(g.LINK, g.HELPER)
        recovered = new.replace(g.PROTOTYPE, g.OLD_SIGNATURE, 1)
        recovered = recovered.replace("\tstruct gps_each_link *p;",
            "\tstruct gps_each_link *p = gps_dl_link_get(link_id);", 1)
        recovered = recovered.replace(g.ZERO_LINK + "\tp = gps_dl_link_get(link_id);\n", "", 1)
        recovered = recovered.replace(g.QUEUED, "", 1).replace(g.UNAVAILABLE, "", 1)
        self.assertEqual(recovered, self.body(g.LINK, "gps_each_link_write_with_opt", fixed=False))

    def test_06_scope_is_one_device_function_one_link_function_and_declaration(self):
        for path, name in ((g.DEVICE, "gps_each_device_write"),
                           (g.LINK, "gps_each_link_write_with_opt")):
            old, new = self.old[path], self.fixed[path]
            before = g.function_span(old, name)
            after = g.function_span(new, name)
            end = g.function_span(new, g.HELPER).end if path == g.LINK else after.end
            self.assertEqual(old[:before.start], new[:after.start])
            self.assertEqual(old[before.end:], new[end:])
        added = ("/* nonblocking skips capacity and completion waits for this call only. */\n"
                 + g.PROTOTYPE + ";\n")
        self.assertEqual(self.fixed[g.LINK_H].replace(added, "", 1), self.old[g.LINK_H])
        self.assertNotIn("poll(", g.PATCH.read_text())
        with self.assertRaises(ValueError):
            g.transform(g.DMA, self.old[g.DMA])

    def test_07_drift_double_application_and_ambiguous_spans_fail_closed(self):
        for path, text in self.fixed.items():
            with self.subTest(path=path), self.assertRaises(ValueError):
                g.transform(path, text)
        for path, needle in ((g.DEVICE, "copy_size = count;"),
                             (g.LINK, "\t\t\t/* TODO: */"),
                             (g.LINK_H, g.OLD_SIGNATURE)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                g.transform(path, self.old[path].replace(needle, "/* drift */", 1))
        sample = '/* target() { } */\nint caller() { return target(); }\nint target(void) { const char *s = "}"; return 1; }\n'
        self.assertTrue(g.function_span(sample, "target").text(sample).startswith("int target"))
        with self.assertRaises(ValueError):
            g.function_span(sample + "int target(int n) { return n; }", "target")

    def test_08_patch_hunk_counts_paths_and_context(self):
        text = g.PATCH.read_text()
        self.assertEqual(re.findall(r"^--- a/(.+)$", text, re.M), list(g.SOURCES))
        hunks = re.findall(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n(.*?)(?=^@@|^diff --git|\Z)", text, re.M | re.S)
        self.assertGreaterEqual(len(hunks), 5)
        for _, old_count, _, new_count, body in hunks:
            lines = body.splitlines()
            self.assertTrue(all(line and line[0] in " +-" for line in lines))
            self.assertEqual(sum(line[0] in " -" for line in lines), int(old_count))
            self.assertEqual(sum(line[0] in " +" for line in lines), int(new_count))
            self.assertTrue(all(line.startswith(" ") for line in lines[:3]))
            self.assertTrue(all(line.startswith(" ") for line in lines[-3:]))

    def check_apply(self, executable=None):
        with tempfile.TemporaryDirectory(prefix="apply-", dir=g.HERE) as directory:
            g.populate(directory)
            root = Path(directory)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            command = ([executable, "--batch", "--fuzz=0", "-p1", "-i", str(g.PATCH)]
                       if executable else ["git", "apply", "--whitespace=error", str(g.PATCH)])
            output = g.checked(command, directory)
            self.assertNotRegex(output.lower(), r"fuzz|offset|skipping")
            for path, data in before.items():
                expected = g.transform(str(path), data.decode()).encode() if str(path) in g.SOURCES else data
                self.assertEqual((root / path).read_bytes(), expected, str(path))
            g.checked(["git", "apply", "--reverse", str(g.PATCH)], directory)
            for path, data in before.items():
                self.assertEqual((root / path).read_bytes(), data)
            g.checked(["git", "apply", str(g.PATCH)], directory)
            with self.assertRaises(ValueError):
                g.checked(["git", "apply", "--check", str(g.PATCH)], directory)

    def test_09_exact_stacked_git_application_reverse_and_double_apply(self):
        self.check_apply()

    def test_10_host_fuzz_zero_stacked_application(self):
        self.check_apply(os.environ.get("TETRIS_GNU_PATCH", "patch"))

    def test_11_gnu_patch_required_in_native_ci(self):
        candidates = (os.environ.get("TETRIS_GNU_PATCH"), shutil.which("gpatch"), shutil.which("patch"))
        for executable in filter(None, candidates):
            result = subprocess.run([executable, "--version"], text=True, capture_output=True)
            if result.returncode == 0 and "GNU patch" in result.stdout:
                self.check_apply(executable)
                return
        if os.environ.get("WRITE_BOUNDARY_REQUIRE_GNU_PATCH") == "1":
            self.fail("CI requires GNU patch")
        self.skipTest("GNU patch unavailable; mandatory in native CI")

    def test_12_fixture_is_exact_stacked_actual_source(self):
        fixture = g.fixture(baseline=self.old)
        names = {g.DEVICE: ("gps_each_device_write",),
                 g.LINK: (g.HELPER, "gps_each_link_write_with_opt", "gps_each_link_write"),
                 g.DMA: ("gdl_dma_buf_put", "gdl_dma_buf_buf_to_entry", "gdl_dma_buf_get_free_entry_inner",
                         "gdl_dma_buf_get_free_entry", "gdl_dma_buf_set_free_entry_inner", "gdl_dma_buf_set_free_entry")}
        for path, functions in names.items():
            text = self.fixed.get(path, self.old[path])
            for name in functions:
                expected = g.function_span(text, name).text(text)
                self.assertEqual(g.function_span(fixture, name).text(fixture), expected)
        self.assertNotIn("gps_each_link_read_with_timeout", fixture)
        types = g.fixture_types()
        self.assertIn("unsigned char o_buf[GPS_DATA_PATH_BUF_MAX];", types)
        self.assertIn("#define GDL_COUNT_FREE", types)
        # Relevant declarations have not changed under prerequisite patches.
        for path, keyword, name in ((g.read.DEVICE_H, "struct", "gps_each_device"),
                                    (g.read.DMA_H, "struct", "gps_dl_dma_buf")):
            self.assertIn(g.read.declaration(g.source(path), keyword, name), types)

    def test_13_mutations_cover_production_guards_and_legacy_contract(self):
        fixture = g.fixture(baseline=self.old)
        mutants = g.mutations(fixture)
        self.assertEqual(len(mutants), 8)
        self.assertEqual(len(set(mutants.values())), 8)
        for mutated in mutants.values():
            self.assertNotEqual(fixture, mutated)
            self.assertEqual(g.function_span(fixture, "gdl_dma_buf_put").text(fixture),
                             g.function_span(mutated, "gdl_dma_buf_put").text(mutated))

    def test_14_native_runner_rejects_local_execution_before_source_checks(self):
        for ci, actions in (("", ""), ("true", ""), ("1", "true"), ("false", "true")):
            result = subprocess.run([sys.executable, "-B", str(g.HERE / "run.py"), "--ci-native"],
                env={**os.environ, "CI": ci, "GITHUB_ACTIONS": actions,
                     "TETRIS_MODULES_TREE": "/no-vendor-tree"}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("native compilation is CI-only", result.stderr)
            self.assertNotIn("test_01", result.stderr)

    def test_15_vendor_override_never_falls_back(self):
        fake = g.HERE / "deliberately-absent-vendor-tree"
        result = subprocess.check_output([sys.executable, "-B", "-c",
            "import generate; print(generate.MODULES)"], cwd=g.HERE, text=True,
            env={**os.environ, "TETRIS_MODULES_TREE": str(fake)})
        self.assertEqual(result.strip(), str(fake))


if __name__ == "__main__":
    unittest.main(verbosity=2)
