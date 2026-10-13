#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Canonical source/mutation and exact-object patch gates. Never compile C."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SIDECAR = HERE.parent / "uboot-segments"
sys.path.insert(0, str(SIDECAR))
import test_flat_metadata as reviewed
from integrate_flat_metadata import BASE_SHA256, integrate, render_patch
from test_ram_admission import SOURCE, function, kernel_source

SHIPPING = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0120-misc-tetris-gpueb-authenticated-ram-analysis.patch"
DEVICE_REV = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES_REV = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"


def git_source(tree, revision, path):
    return subprocess.check_output(
        ["git", "-C", str(tree), "show", f"{revision}:{path}"],
        text=True, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


class CanonicalMetadata(reviewed.FlatMetadata):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SIDECAR / "FLAT-METADATA-PRODUCER.json").read_text())
        cls.header = (SIDECAR / "tetris_gpueb_flat_metadata.h").read_text()
        cls.integrated = SOURCE
        # Recover only the pinned old consumer for the reviewed migration tests.
        # All admission/mutation checks run against the real canonical source.
        with tempfile.TemporaryDirectory(prefix="gpueb-metadata-base-") as directory:
            target = Path(directory) / "patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c"
            target.parent.mkdir(parents=True)
            target.write_text(SOURCE)
            subprocess.run(["patch", "--batch", "--fuzz=0", "-R", "-p1", "-i",
                            str(SIDECAR / "flat-metadata-integration.patch")],
                           cwd=directory, check=True, capture_output=True, text=True)
            cls.original = target.read_text()
        if hashlib.sha256(cls.original.encode()).hexdigest() != BASE_SHA256:
            raise ValueError("reverse migration did not recover the reviewed base")
        if integrate(cls.original, cls.header) != SOURCE:
            raise ValueError("canonical source differs from reviewed v1 integration")
        tree = Path(os.environ.get("TETRIS_UBOOT_TREE", ROOT.parent / "u-boot-mt6878"))
        board = tree / cls.manifest["board_directory"]
        cls.producer = {name: (board / name).read_text() for name in cls.manifest["sources"]}
        spec = importlib.util.spec_from_file_location("canonical_ram_admission", HERE / "test_ram_admission.py")
        cls.ram = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ram)

    def test_cli_renders_without_writing_parent_files(self):
        before = hashlib.sha256((HERE / "gpueb-flat-analysis.c").read_bytes()).digest()
        # The staging CLI deliberately refuses to stack admission a second time.
        for mode in ("source", "patch", "delta"):
            result = subprocess.run([sys.executable, "-B", str(SIDECAR / "integrate_flat_metadata.py"),
                                     "--format", mode], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("existing consumer changed; reconcile", result.stderr)
        self.assertEqual(hashlib.sha256((HERE / "gpueb-flat-analysis.c").read_bytes()).digest(), before)

    def test_canonical_source_and_audit_pin_match_shipping_patch(self):
        self.assertEqual(SHIPPING.read_text(), render_patch(SOURCE))
        audit = ast.parse((HERE.parent / "audit_gpueb_b41.py").read_text())
        pins = next(ast.literal_eval(node.value) for node in audit.body
                    if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "RETAINED_SOURCES"
                        for target in node.targets))
        for name, digest in pins.items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), digest, name)
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(),
                         "e0ac3e88c4a23faabf0cc80f406a52e7eda1ac44af0f9004df65de730a367204")

    def test_package_applies_without_fuzz_to_exact_linux_objects(self):
        with tempfile.TemporaryDirectory(prefix="gpueb-package-apply-") as directory:
            tree = Path(directory)
            for name in ("Kconfig", "Makefile"):
                path = tree / "drivers/misc" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(kernel_source("drivers/misc/" + name))
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(SHIPPING)],
                                    cwd=tree, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("offset", result.stdout)
            self.assertNotIn("fuzz", result.stdout)
            self.assertEqual((tree / "drivers/misc/gpueb-flat-analysis.c").read_text(), SOURCE)
            self.assertEqual((tree / "drivers/misc/Kconfig").read_text().count(
                "config TETRIS_GPUEB_FLAT_ANALYSIS"), 1)
            self.assertEqual((tree / "drivers/misc/Makefile").read_text().count(
                "obj-$(CONFIG_TETRIS_GPUEB_FLAT_ANALYSIS) += gpueb-flat-analysis.o"), 1)

    def test_runtime_probe_has_no_write_or_start_entry(self):
        self.assertIn(".probe = flat_bound_probe", SOURCE)
        self.assertIn("module_platform_driver(flat_driver)", SOURCE)
        fops = SOURCE.split("static const struct file_operations flat_fops =", 1)[1].split("};", 1)[0]
        self.assertNotRegex(fops, r"\.(?:write|mmap|unlocked_ioctl|compat_ioctl)\s*=")
        self.assertNotRegex(self.ram.without_comments(SOURCE),
                            r"\b(?:memcpy_toio|memset_io|iowrite\w*|writel\w*|"
                            r"enable_irq|request_irq|rproc_boot|arm_smccc_smc|"
                            r"regulator_enable|clk_prepare_enable|pm_runtime\w*)\s*\(")


class PinnedRuntimeDependencies(unittest.TestCase):
    def test_nos41_gpueb_probe_requires_distinct_ipi_and_dram_owners(self):
        tree = Path(os.environ.get("TETRIS_DEVICE_MODULES_TREE",
                                   ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878"))
        prefix = "drivers/gpu/mediatek/gpueb/"
        init = git_source(tree, DEVICE_REV, prefix + "gpueb_init.c")
        probe = function(init, "__mt_gpueb_pdrv_probe")
        self.assertLess(probe.index("gpueb_ipi_init(pdev)"), probe.index("gpueb_reserved_mem_init(pdev)"))
        ipi = function(git_source(tree, DEVICE_REV, prefix + "gpueb_ipi.c"), "gpueb_ipi_init")
        for term in ("mtk_mbox_probe(", "enable_irq_wake(", "mtk_smem_init(", "mtk_ipi_device_register("):
            self.assertIn(term, ipi)
        memory = function(git_source(tree, DEVICE_REV, prefix + "gpueb_reserved_mem.c"),
                          "gpueb_reserved_mem_init")
        for term in ('"gpueb_mem_addr"', '"gpueb_mem_size"', '"gpueb-mem-table"', "ioremap_wc("):
            self.assertIn(term, memory)
        # The diagnostic consumer supplies none of the vendor runtime ABI.
        for term in ('"gpueb_mem_addr"', '"gpueb_mem_size"', "mtk_ipi_device_register("):
            self.assertNotIn(term, SOURCE)

    def test_nos41_mali_build_selector_is_not_panthor_integration(self):
        tree = Path(os.environ.get("TETRIS_VENDOR_MODULES_TREE",
                                   ROOT.parent / "android_kernel_modules_nothing_mt6878"))
        makefile = git_source(tree, MODULES_REV, "gpu/mt6878/Makefile")
        self.assertIn("export MTK_PLATFORM_VERSION := mt6878", makefile)
        self.assertIn("mali_avalon/mali-r44p1/drivers/gpu/arm/midgard/", makefile)
        self.assertEqual(git_source(tree, MODULES_REV, "gpu/mt6878/mali_avalon"),
                         "../gpu_mali/mali_avalon/")
        self.assertNotIn("panthor", makefile)


if __name__ == "__main__":
    unittest.main()
