#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

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
        self.kernel = self.root / "linux"
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
        other = self.root / "other"
        (other / "include/config").mkdir(parents=True)
        (other / "Module.symvers").write_text("fixture")
        (other / "include/config/kernel.release").write_text("fixture")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_wrong_config(self):
        (self.kernel / ".config").write_text("# CONFIG_ARM64 is not set\n")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_invalid_exports(self):
        (self.kernel / "Module.symvers").write_text("invalid\n")
        with self.assertRaises(ValueError):
            self.run_collect()

    def test_invalid_commit(self):
        with self.assertRaises(ValueError):
            collector.collect(self.root, self.out, "main")


if __name__ == "__main__":
    unittest.main()
