#!/usr/bin/env python3
"""Exercise real patch dry-run and exact-copy rejection without compiling C."""
import json
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECK = HERE / "check-staging.py"
ARCHIVE = None
if "--kernel-archive" in sys.argv:
    index = sys.argv.index("--kernel-archive")
    ARCHIVE = Path(sys.argv[index + 1]).resolve()
    del sys.argv[index:index + 2]


def run(*args):
    return subprocess.run([sys.executable, str(CHECK), *map(str, args)],
                          text=True, capture_output=True)


class StagingTests(unittest.TestCase):
    def test_reject_old_noncanonical_hunk(self):
        spec = importlib.util.spec_from_file_location("cam_main_staging", CHECK)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        package = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
        section = (package / "0092-clk-mediatek-mt6878-camera-main.patch").read_text().split(
            "+++ b/drivers/clk/mediatek/clk-mt6878-cam.c\n", 1)[1]
        base = "\n".join(line[1:] for line in section.splitlines()
                         if line.startswith("+") and not line.startswith("+++")) + "\n"
        overlay = (HERE / "provider.patch").read_text()
        old = overlay.replace("@@ -75,12 +75,15 @@", "@@ -74,11 +74,14 @@")
        old = old.replace(" module_platform_driver(clk_mt6878_cam_drv);\n", "")
        with self.assertRaises(ValueError):
            checker.overlay_text(base, old)

    @unittest.skipUnless(ARCHIVE, "pass --kernel-archive for fresh packaged-source replay")
    def test_fresh_packaged_clock_closure(self):
        package = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
        apkbuild = (package / "APKBUILD").read_text()
        commit = re.search(r'^_commit="([0-9a-f]{40})"$', apkbuild, re.M)[1]
        entries = re.search(r'^source="\n(.*?)^"$', apkbuild, re.M | re.S)[1].split()
        patches = [entry for entry in entries if entry.endswith(".patch")]
        targets = {"drivers/clk/mediatek/Kconfig", "drivers/clk/mediatek/Makefile",
                   "drivers/clk/mediatek/clk-mt6878-cam.c"}
        with tempfile.TemporaryDirectory(prefix="cam-main-packaged-") as name:
            tree = Path(name)
            with tarfile.open(ARCHIVE) as archive:
                for target in sorted(targets - {"drivers/clk/mediatek/clk-mt6878-cam.c"}):
                    member = archive.getmember(f"linux-{commit}/{target}")
                    destination = tree / target
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.extractfile(member).read())
            # Replay ALL shipped patch fragments touching the clock closure,
            # in APKBUILD order, on actual pristine archive inputs (no C).
            for filename in patches:
                text = (package / filename).read_bytes()
                fragments = re.split(rb"(?=^diff --git )", text, flags=re.M)
                selected = []
                for fragment in fragments:
                    match = re.search(rb'^\+\+\+ b/(\S+)$', fragment, re.M)
                    if match and match[1].decode("ascii") in targets:
                        selected.append(fragment)
                if selected:
                    result = subprocess.run(["patch", "--batch", "-p1"], cwd=tree,
                                            input=b"".join(selected), capture_output=True)
                    self.assertEqual(result.returncode, 0,
                                     f"{filename}: {result.stdout}\n{result.stderr}")
            result = run("--kernel-tree", tree)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Independent git parser, in addition to the system patch parser.
            result = subprocess.run(["git", "apply", "--check", str(HERE / "provider.patch")],
                                    cwd=tree, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_packaged_overlay_and_exact_copies(self):
        plan = run("--plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        manifest = json.loads(plan.stdout)
        package = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
        section = (package / manifest["requires_packaged_patch"]).read_text().split(
            f"+++ b/{manifest['overlay_target']}\n", 1)[1]
        base = "\n".join(line[1:] for line in section.splitlines()
                         if line.startswith("+") and not line.startswith("+++")) + "\n"
        # Mechanical throw-away extraction/copy of actual reviewed sources.
        with tempfile.TemporaryDirectory(prefix="cam-main-overlay-") as name:
            tree = Path(name)
            provider = tree / manifest["overlay_target"]
            provider.parent.mkdir(parents=True)
            provider.write_text(base)
            result = run("--kernel-tree", tree)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1"],
                           cwd=tree, input=(ROOT / manifest["overlay"]).read_text(),
                           text=True, capture_output=True, check=True)
            for source, destination in manifest["sources"].items():
                target = tree / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, target)
            result = run("--staged-tree", tree)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Never accept applying the overlay again or corrupted copies.
            self.assertNotEqual(run("--kernel-tree", tree).returncode, 0)
            destination = next(iter(manifest["sources"].values()))
            (tree / destination).write_text("not the reviewed input\n")
            self.assertNotEqual(run("--staged-tree", tree).returncode, 0)


if __name__ == "__main__":
    unittest.main()
