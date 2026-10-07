#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "collector", Path(__file__).parents[1] / "collect-kernel-build-evidence.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "build"
        self.out = Path(self.temp.name) / "out"
        self.sources = self.root / "chroot_native/home/pmos/build/src"
        self.kernel = self.sources / "linux"
        for name in collector.FILES:
            path = self.kernel / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        (self.kernel / ".config").write_text("CONFIG_ARM64=y\n")
        (self.kernel / "Module.symvers").write_text(
            "0x12345678\tprintk\tvmlinux\tEXPORT_SYMBOL\t\n")

    def run_collect(self):
        return collector.collect(self.root, self.out, "a" * 40)

    def test_complete(self):
        result = self.run_collect()
        self.assertEqual(len(result["sha256"]), len(collector.FILES))
        self.assertEqual((self.out / ".config").read_bytes(),
                         (self.kernel / ".config").read_bytes())

    def test_missing(self):
        (self.kernel / "System.map").unlink()
        with self.assertRaises(ValueError):
            self.run_collect()
        self.assertFalse(self.out.exists())

    def test_ambiguous(self):
        other = self.sources / "other"
        (other / "include/config").mkdir(parents=True)
        (other / "Module.symvers").write_text("fixture")
        (other / "include/config/kernel.release").write_text("fixture")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_wrong_config(self):
        (self.kernel / ".config").write_text("# CONFIG_ARM64 is not set\n")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_no_recursive_chroot_scan(self):
        # The old collector fails before finding the kernel on live procfs.
        with patch.object(Path, "rglob", side_effect=OSError(22, "Invalid argument")):
            self.assertEqual(len(self.run_collect()["sha256"]), len(collector.FILES))

    def test_ignore_mounted_trees(self):
        for directory in ("proc/72/task/72/net", "sys", "dev", "mnt/pmbootstrap"):
            other = self.root / "chroot_native" / directory / "linux"
            (other / "include/config").mkdir(parents=True)
            (other / "Module.symvers").write_text("decoy")
            (other / "include/config/kernel.release").write_text("decoy")
        self.run_collect()

    def test_cross_chroot_ambiguity(self):
        other = self.root / "chroot_buildroot_aarch64/home/pmos/build/src/linux"
        (other / "include/config").mkdir(parents=True)
        (other / "Module.symvers").write_text("fixture")
        (other / "include/config/kernel.release").write_text("fixture")
        with self.assertRaisesRegex(ValueError, "found 2"):
            self.run_collect()

    def test_invalid_exports(self):
        (self.kernel / "Module.symvers").write_text("invalid\n")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_invalid_commit(self):
        with self.assertRaises(ValueError):
            collector.collect(self.root, self.out, "main")

    def cleanup_after_build(self, retain):
        # abuild sources APKBUILD after its configuration and then runs
        # cleanup $CLEANUP after a successful build, before our CI collector.
        config = 'CLEANUP="srcdir pkgdir tmpdir"\n'
        if retain:
            suffix = Path(__file__).parents[2] / "ci/retain-kernel-evidence.abuild"
            config += suffix.read_text()
        config += '\nprintf "%s" "$CLEANUP"\n'
        targets = subprocess.check_output(["sh", "-c", config], text=True).split()
        build = self.sources.parent
        for name in targets:
            relative = {"srcdir": "src", "pkgdir": "pkg", "tmpdir": "tmp"}[name]
            directory = build / relative
            if directory.exists():
                shutil.rmtree(directory)

    def test_reproduce_successful_build_cleanup(self):
        self.cleanup_after_build(retain=False)
        with self.assertRaisesRegex(ValueError, "found 0"):
            self.run_collect()
        self.assertFalse(self.out.exists())

    def test_ci_retains_evidence_after_successful_build(self):
        self.cleanup_after_build(retain=True)
        result = self.run_collect()
        self.assertEqual(len(result["sha256"]), len(collector.FILES))

    def test_ci_suffix_precedes_kernel_build(self):
        workflow = (Path(__file__).parents[2] / ".github/workflows/ci.yml").read_text()
        start = workflow.index("      - name: Build kernel package\n")
        end = workflow.index("      - name: Preserve configured kernel exports and DTB\n")
        build = workflow[start:end]
        self.assertLess(build.index("cat /work/ci/retain-kernel-evidence.abuild"),
                        build.index("build --force --lax linux-postmarketos-mediatek-mt6878"))
        self.assertIn("/work/upstream/pmaports/device/testing/"
                      "linux-postmarketos-mediatek-mt6878/APKBUILD", build)


if __name__ == "__main__":
    unittest.main()
