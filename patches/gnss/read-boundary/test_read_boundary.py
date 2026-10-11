#!/usr/bin/env python3
"""Local structural/application tests. Never invokes any native compiler."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import generate as g

MODULES = Path(os.environ.get("READ_BOUNDARY_MODULES", str(g.MODULES)))
STACK = sorted(g.PACKAGE.glob("100[1-7]-*.patch.vendor"))


def run(argv, cwd):
    # Disposable fixtures live inside the allowed subtree, but must not inherit
    # the surrounding repository prefix (git apply would silently skip paths).
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(cwd).parent), LC_ALL="C")
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"{argv}:\n{result.stdout}{result.stderr}")
    return result.stdout + result.stderr


def populate(directory, stack=False):
    paths = {g.DEVICE, g.LINK}
    added = set()
    if stack:
        for patch in STACK:
            text = patch.read_text()
            paths.update(re.findall(r"^--- a/(.+)$", text, re.M))
            added.update(re.findall(r"^--- /dev/null\n\+\+\+ b/(.+)$", text, re.M))
    for path in paths - added:
        dest = Path(directory) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(subprocess.check_output(
            ["git", "-C", str(MODULES), "show", f"{g.PIN}:{path}"]))
    if stack:
        for patch in STACK:
            if patch.name.startswith("1005-"):
                clock = Path(directory) / (g.BASE + "linux/gps_dl_linux_clock_mng.c")
                clock.write_bytes(clock.read_bytes().replace(b"\r\n", b"\n"))
            # Match APKBUILD's patch engine; existing 1002 has hunk counts that
            # git apply rejects. Never repair or rewrite the existing series.
            output = run([os.environ.get("TETRIS_GNU_PATCH", "patch"),
                          "--batch", "--fuzz=0", "-p1", "-i", str(patch)], directory)
            if re.search(r"fuzz", output, re.I):
                raise AssertionError(output)


class ReadBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = {p: g.source(p, MODULES) for p in (g.DEVICE, g.LINK)}
        cls.fixed = {p: g.transform(p, text) for p, text in cls.old.items()}

    def test_01_generated_patch_is_current(self):
        self.assertEqual(g.PATCH.read_text(), g.generate(MODULES))
        self.assertEqual(len(STACK), 7)

    def test_02_balanced_spans_ignore_comments_strings_calls(self):
        sample = '/* target() { } */\nint caller() { return target(); }\nint target(void)\n{ const char *s = "}\\\"{"; /* { */ return 1; }\n'
        span = g.function_span(sample, "target")
        self.assertTrue(span.text(sample).startswith("int target(void)"))
        self.assertTrue(span.text(sample).endswith("return 1; }"))
        with self.assertRaises(ValueError):
            g.function_span(sample + "int target(int n) { return n; }", "target")
        with self.assertRaises(ValueError):
            g.function_span("int target(void) {", "target")

    def test_03_drift_and_double_application_fail_closed(self):
        for path, text in self.fixed.items():
            with self.subTest(path=path), self.assertRaises(ValueError):
                g.transform(path, text)
        changed = self.old[g.DEVICE].replace(
            "gps_each_link_read(link_id, &dev->i_buf[0], count)",
            "gps_each_link_read(link_id, dev->i_buf, count)")
        with self.assertRaises(ValueError):
            g.transform(g.DEVICE, changed)

    def test_04_device_zero_bound_and_dispatch_order(self):
        text = g.function_span(self.fixed[g.DEVICE], "gps_each_device_read").text(self.fixed[g.DEVICE])
        zero = text.index("if (!count)\n\t\treturn 0;")
        self.assertLess(zero, text.index("filp->private_data"))
        bound = text.index("if (count > sizeof(dev->i_buf))\n\t\tcount = sizeof(dev->i_buf);")
        self.assertLess(bound, text.index("gps_each_link_rec_read"))
        self.assertLess(bound, text.index("gps_each_link_read_with_timeout"))
        self.assertIn("if (filp->f_flags & O_NONBLOCK)\n"
                      "\t\tretlen = gps_each_link_read_with_timeout(link_id,\n"
                      "\t\t\t&dev->i_buf[0], count, 0, NULL);\n"
                      "\telse\n\t\tretlen = gps_each_link_read(link_id, &dev->i_buf[0], count);", text)
        self.assertIn("retlen = -EFAULT;", text)
        self.assertIn("copy_to_user(buf, &dev->i_buf[0], retlen)", text)

    def test_05_no_data_zero_timeout_before_every_wait(self):
        text = self.fixed[g.LINK]
        read = g.function_span(text, "gps_each_link_read_with_timeout").text(text)
        branch = read.index("} else if (gdl_ret == GDL_FAIL_NODATA) {")
        guard = read.index("if (timeout_usec == 0)\n\t\t\t\treturn -EAGAIN;", branch)
        self.assertLess(read.index("gdl_dma_buf_get("), guard)
        for wait in ("gps_dl_link_wait_on", "gps_dl_hal_wait_and_handle_until_usrt_has_data",
                     "gps_dl_hal_wait_and_handle_until_usrt_has_nodata_or_rx_dma_done"):
            self.assertLess(guard, read.index(wait, branch))

    def test_06_only_two_function_bodies_change(self):
        for path, name in ((g.DEVICE, "gps_each_device_read"),
                           (g.LINK, "gps_each_link_read_with_timeout")):
            old, new = self.old[path], self.fixed[path]
            before, after = g.function_span(old, name), g.function_span(new, name)
            self.assertEqual(old[:before.start], new[:after.start])
            self.assertEqual(old[before.end:], new[after.end:])
        old = g.function_span(self.old[g.LINK], "gps_each_link_read").text(self.old[g.LINK])
        self.assertIn("GPS_DL_RW_NO_TIMEOUT, NULL", old)
        # Removing the inserted guard must recover the entire original link body.
        self.assertEqual(self.old[g.LINK], self.fixed[g.LINK].replace(
            "\t\t\tif (timeout_usec == 0)\n\t\t\t\treturn -EAGAIN;\n\n", "", 1))

    def test_07_hunk_counts_paths_and_context(self):
        text = g.PATCH.read_text()
        self.assertEqual(re.findall(r"^--- a/(.+)$", text, re.M), [g.DEVICE, g.LINK])
        hunks = re.findall(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n(.*?)(?=^@@|^diff --git|\Z)", text, re.M | re.S)
        self.assertEqual(len(hunks), 3)
        for _, old_count, _, new_count, body in hunks:
            lines = body.splitlines()
            self.assertTrue(all(line and line[0] in " +-" for line in lines))
            self.assertEqual(sum(line[0] in " -" for line in lines), int(old_count))
            self.assertEqual(sum(line[0] in " +" for line in lines), int(new_count))
            self.assertTrue(all(line.startswith(" ") for line in lines[:3]))
            self.assertTrue(all(line.startswith(" ") for line in lines[-3:]))

    def check_apply(self, command, stack):
        with tempfile.TemporaryDirectory(prefix="apply-", dir=g.HERE) as directory:
            populate(directory, stack)
            original = {p: (Path(directory) / p).read_bytes() for p in self.old}
            run(command, directory)
            for path, before in original.items():
                applied = (Path(directory) / path).read_bytes()
                self.assertEqual(applied, g.transform(path, before.decode()).encode())
                name = "gps_each_device_read" if path == g.DEVICE else "gps_each_link_read_with_timeout"
                # Prior package patches must not make the compiled fixture a
                # different implementation from the staged production body.
                self.assertEqual(g.function_span(applied.decode(), name).text(applied.decode()),
                    g.function_span(self.fixed[path], name).text(self.fixed[path]))
            run(["git", "apply", "--reverse", str(g.PATCH)], directory)
            for path, before in original.items():
                self.assertEqual((Path(directory) / path).read_bytes(), before)

    def test_08_raw_git_apply_and_reverse(self):
        self.check_apply(["git", "apply", "--whitespace=error", str(g.PATCH)], False)

    def test_09_stacked_git_apply_and_reverse(self):
        self.check_apply(["git", "apply", "--whitespace=error", str(g.PATCH)], True)

    def test_10_gnu_fuzz_zero_raw_and_stack(self):
        candidates = (os.environ.get("TETRIS_GNU_PATCH"), shutil.which("gpatch"), shutil.which("patch"))
        for executable in filter(None, candidates):
            result = subprocess.run([executable, "--version"], text=True, capture_output=True)
            if result.returncode == 0 and "GNU patch" in result.stdout:
                for stack in (False, True):
                    self.check_apply([executable, "--batch", "--fuzz=0", "-p1", "-i", str(g.PATCH)], stack)
                return
        if os.environ.get("READ_BOUNDARY_REQUIRE_GNU_PATCH") == "1":
            self.fail("CI requires GNU patch")
        self.skipTest("GNU patch unavailable; mandatory in CI")

    def test_11_native_fixture_contains_exact_production_functions(self):
        fixture = g.fixture(MODULES)
        for path, name in ((g.DEVICE, "gps_each_device_read"),
                           (g.LINK, "gps_each_link_read_with_timeout"),
                           (g.DMA, "gdl_dma_buf_get"), (g.DMA, "gdl_dma_buf_entry_to_buf")):
            text = self.fixed.get(path, g.source(path, MODULES))
            self.assertIn(g.function_span(text, name).text(text), fixture)
        types = g.fixture_types(MODULES)
        self.assertIn("unsigned char i_buf[GPS_DATA_PATH_BUF_MAX];", types)
        self.assertIn("#define GPS_DATA_PATH_BUF_MAX\t2048", types)
        self.assertIn("struct gps_dl_dma_buf {", types)

    def test_12_manifest_and_package_vendor_pin(self):
        manifest = json.loads((g.HERE / "STAGING.json").read_text())
        self.assertEqual(manifest["connectivity_commit"], g.PIN)
        self.assertEqual(manifest["patch_sha512"], hashlib.sha512(g.PATCH.read_bytes()).hexdigest())
        # Main owns package activation; this gate must keep working after 1008
        # is added to source/prepare/checksums without changing the vendor pin.
        apkbuild = (g.PACKAGE / "APKBUILD").read_text()
        self.assertIn('_connmods_commit="' + g.PIN + '"', apkbuild)

    def test_13_explicit_vendor_environment_never_falls_back(self):
        fake = g.HERE / "deliberately-absent-vendor-tree"
        command = "import runpy; m=runpy.run_path(" + repr(str(g.HERE / "generate.py")) + "); print(m['MODULES'])"
        result = subprocess.check_output([os.sys.executable, "-B", "-c", command], text=True,
            env={**os.environ, "TETRIS_MODULES_TREE": str(fake)})
        self.assertEqual(result.strip(), str(fake))

    def test_package_and_required_ci_integration(self):
        source = (g.PACKAGE / "APKBUILD").read_text()
        self.assertIn('\t' + g.PATCH.name + '\n', source)
        self.assertIn('patch --fuzz=0 -p1 -d "$_connmods_dir" \\\n\t\t< "$srcdir"/' + g.PATCH.name, source)
        self.assertIn(hashlib.sha512(g.PATCH.read_bytes()).hexdigest() + '  ' + g.PATCH.name, source)
        workflow = (g.ROOT / '.github/workflows/ci.yml').read_text()
        start = workflow.index('      - name: Validate real GPS data-link read semantics\n')
        step = workflow[start:workflow.index('      - name:', start + 10)]
        self.assertIn('python3 -B patches/gnss/read-boundary/run.py --ci-native', step)
        self.assertNotIn('continue-on-error', step)

    def test_14_native_runner_rejects_local_execution_before_checks(self):
        for ci, actions in (("", ""), ("true", ""), ("1", "true"), ("false", "true")):
            with self.subTest(CI=ci, GITHUB_ACTIONS=actions):
                result = subprocess.run([os.sys.executable, "-B", str(g.HERE / "run.py"), "--ci-native"],
                    env={**os.environ, "CI": ci, "GITHUB_ACTIONS": actions,
                         "TETRIS_MODULES_TREE": "/no-vendor-tree"}, text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("native compilation is CI-only", result.stderr)
                self.assertNotIn("test_01", result.stderr)

    def test_15_host_fuzz_zero_raw_and_stacked(self):
        for stack in (False, True):
            self.check_apply([os.environ.get("TETRIS_GNU_PATCH", "patch"),
                              "--batch", "--fuzz=0", "-p1", "-i", str(g.PATCH)], stack)

    def test_16_recorded_dma_ownership_and_production_reachability(self):
        header = g.source(g.DEVICE_H, MODULES)
        dev = g.declaration(header, "struct", "gps_each_device")
        self.assertIn("unsigned char i_buf[GPS_DATA_PATH_BUF_MAX];", dev)
        self.assertNotIn("mutex", dev)
        dma = g.source(g.DMA, MODULES)
        acquire = g.function_span(dma, "gdl_dma_buf_get_data_entry").text(dma)
        self.assertIn("gps_dl_dma_buf_lock_take", acquire)
        complete = g.function_span(dma, "gdl_dma_buf_set_data_entry_inner").text(dma)
        self.assertIn("p_dma->reader_working = false;", complete)
        get = g.function_span(dma, "gdl_dma_buf_get").text(dma)
        self.assertIn("gdl_dma_buf_set_data_entry(p_dma, p_entry);", get)
        kbuild = g.source(g.BASE + "plat/v051/Kbuild", MODULES)
        for obj in ("linux/gps_each_device.o", "gps_each_link.o", "lib/gps_dl_dma_buf.o", "link/gps_dl_link_sync.o"):
            self.assertIn(obj, kbuild)


if __name__ == "__main__":
    unittest.main(verbosity=2)
