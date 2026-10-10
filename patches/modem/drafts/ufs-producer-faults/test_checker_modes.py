#!/usr/bin/env python3
"""Read-only Python source checks: old baseline, integrated files, rejected drift."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from check_producer_faults import module, HERE


class Modes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uboot = Path(sys.argv[1]).resolve()
        cls.check = module("startup_modes", HERE.parent / "startup-final/check_startup_final.py")
        cls.read = Path.read_text
        cls.exists = Path.exists
        cls.baseline = {}
        for name in ("tetris_modem_storage.c", "tetris_modem_storage.h", "tetris_modem_loaded_boot.c", "mt6878_tetris.c"):
            path = cls.check.BOARD + name
            cls.baseline[str(cls.uboot / path)] = subprocess.check_output([
                "git", "-C", str(cls.uboot), "show", f"{cls.check.BASE}:{path}"]).decode()
        config = "arch/arm/mach-mediatek/Kconfig"
        cls.baseline[str(cls.uboot / config)] = subprocess.check_output([
            "git", "-C", str(cls.uboot), "show", f"{cls.check.BASE}:{config}"]).decode()
        cls.integrated = dict(cls.baseline)
        for name in ("unified-storage.patch", "owned-loader.patch", "board-brom-only.patch"):
            for section in (cls.check.HERE / name).read_text().split("diff --git ")[1:]:
                path = str(cls.uboot / section.splitlines()[0].split(" b/", 1)[1])
                cls.integrated[path] = cls.check.apply_file(cls.baseline[path], section)
        for name in ("tetris_modem_final.c", "tetris_modem_final.h", "tetris_modem_brom_board.c"):
            cls.integrated[str(cls.uboot / cls.check.BOARD / name)] = (cls.check.HERE / name).read_text()
        cls.integrated[str(cls.uboot / config)] += "\n" + (cls.check.HERE / "brom-only.Kconfig").read_text()

    def check_tree(self, contents):
        def read(path, *args, **kwargs):
            key = str(path.resolve())
            return contents[key] if key in contents else type(self).read(path, *args, **kwargs)

        def exists(path):
            key = str(path.resolve())
            if key in type(self).integrated:
                return key in contents
            return type(self).exists(path)

        with patch.object(Path, "read_text", read), patch.object(Path, "exists", exists), contextlib.redirect_stdout(io.StringIO()):
            self.check.reviewed_sources(self.uboot)
            source = self.check.patched_storage(self.uboot)
            self.assertEqual(source.count("tetris_modem_prepare_bundle_b41("), 1)
            self.assertEqual(source.count("release_staging("), 1)

    def test_baseline_overlay(self):
        self.check_tree(self.baseline)

    def test_integrated_exact(self):
        self.check_tree(self.integrated)

    def test_owner_drift_rejected(self):
        changed = dict(self.integrated)
        path = str(self.uboot / self.check.BOARD / "tetris_modem_loaded_boot.c")
        changed[path] = changed[path].replace("ret = cold_off();", "ret = 0;")
        with self.assertRaises(AssertionError):
            self.check_tree(changed)

    def test_storage_drift_rejected(self):
        changed = dict(self.integrated)
        path = str(self.uboot / self.check.BOARD / "tetris_modem_storage.c")
        changed[path] = changed[path].replace("release_ret = release_staging", "release_ret = NOT_release_staging")
        with self.assertRaises(AssertionError):
            self.check_tree(changed)

    def test_publisher_drift_rejected(self):
        changed = dict(self.integrated)
        path = str(self.uboot / self.check.BOARD / "tetris_modem_final.c")
        changed[path] = changed[path].replace("TAG_CAPACITY 65536UL", "TAG_CAPACITY 2048UL")
        with self.assertRaises(AssertionError):
            self.check_tree(changed)

    def test_default_on_rejected(self):
        changed = dict(self.integrated)
        path = str(self.uboot / "arch/arm/mach-mediatek/Kconfig")
        changed[path] = changed[path].replace("default n\n", "default y\n")
        with self.assertRaises(AssertionError):
            self.check_tree(changed)

    def test_board_gate_drift_rejected(self):
        changed = dict(self.integrated)
        path = str(self.uboot / self.check.BOARD / "mt6878_tetris.c")
        changed[path] = changed[path].replace("CONFIG_TETRIS_MODEM_BROM_ONLY", "CONFIG_NOT_THE_BROM_GATE")
        with self.assertRaises(AssertionError):
            self.check_tree(changed)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_checker_modes.py UBOOT_TREE")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Modes)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
