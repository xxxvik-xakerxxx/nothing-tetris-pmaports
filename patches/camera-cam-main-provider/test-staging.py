#!/usr/bin/env python3
"""Exercise real patch dry-run and exact-copy rejection without compiling C."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECK = HERE / "check-staging.py"


def run(*args):
    return subprocess.run([sys.executable, str(CHECK), *map(str, args)],
                          text=True, capture_output=True)


class StagingTests(unittest.TestCase):
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
