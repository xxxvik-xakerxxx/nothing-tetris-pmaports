#!/usr/bin/env python3
"""Exercise the real object runner's CAMISP overlays without a compiler."""
import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


smoke = module("camisp_smoke", ROOT / "ci/kernel-object-smoke.py")
generate = module("camisp_generate", HERE / "generate-overlays.py")


class Staging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="camisp-staging-test-")
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        smoke.stage_research_sources(self.tree, ROOT)
        sources = generate.prepared_sources(KERNEL)
        for name, contents in zip(("drivers/memory/mtk-smi.c", "drivers/iommu/mtk_iommu.c"), sources):
            target = self.tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)

    def test_real_overlay_and_exact_staged_closure(self):
        smoke.stage_camisp(self.tree, ROOT)
        for source, destination in smoke.CAMISP_PLAN["sources"].items():
            self.assertEqual((ROOT / source).read_bytes(), (self.tree / destination).read_bytes())
        physical = (self.tree / "drivers/memory/mtk-smi.c").read_text()
        self.assertIn("camisp_larb_resume(larb)", physical)
        self.assertIn("camisp_larb_link_common(dev", physical)
        self.assertIn("camisp_common_resume(common)", physical)
        self.assertNotIn("camisp_pm_lease", physical)
        for name in smoke.CAMISP_PLAN["research_objects"]:
            makefile = self.tree / Path(name).parent / "Makefile"
            self.assertIn(Path(name).name, makefile.read_text())

    def test_regeneration_is_byte_identical(self):
        for name, contents in generate.overlays(KERNEL).items():
            self.assertEqual((HERE / name).read_text(), contents)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path, default=ROOT.parent / ("linux-" + generate.COMMIT))
    args, rest = parser.parse_known_args()
    KERNEL = args.kernel_tree
    unittest.main(argv=[__file__, *rest])
