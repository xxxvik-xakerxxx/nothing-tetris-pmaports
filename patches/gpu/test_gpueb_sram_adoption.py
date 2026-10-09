#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact caller stack migration and adoption checks, no local compilation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prepare_native import definition
from test_gpueb_power import require_exact_application
from test_supply_inventory import validate_hunk_counts

HERE = Path(__file__).resolve().parent
ADOPTION = HERE / "sram-adoption"
sys.path.insert(0, str(ADOPTION))
from prepare_migration import inputs_and_outputs, migration_patch, MAILBOX, DRIVER


class AdoptionTests(unittest.TestCase):
    def test_exact_generated_patch_and_zero_offset_application(self):
        patch = migration_patch()
        self.assertEqual((ADOPTION / "caller-migration.patch").read_text(), patch)
        validate_hunk_counts(patch, "candidate-parent-adoption")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (before, _) in inputs_and_outputs().items():
                path = Path(tmp) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(before)
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=tmp,
                                    input=patch, text=True, capture_output=True)
            require_exact_application(result)
            for name, (_, after) in inputs_and_outputs().items():
                self.assertEqual((Path(tmp) / name).read_text(), after)

    def test_mt6878_mailbox_stops_before_clock_irq_mapping(self):
        source = inputs_and_outputs()[MAILBOX][1]
        probe = definition(source, "static int mtk_gpueb_mbox_probe(")
        gate = probe.index("mt6878_gpueb_adoption_io_gate(")
        for operation in ("platform_get_irq(", "devm_clk_get_prepared(",
                          "devm_platform_ioremap_resource("):
            self.assertLess(gate, probe.index(operation))
        self.assertIn("return ret ? ret : -EOPNOTSUPP", probe[:probe.index("platform_get_irq(")])
        self.assertIn(".parent_owned = true", source)
        self.assertIn(".num_channels = 12", source)  # MT8196 retained

    def test_session_replaces_gpr_claim_before_boot(self):
        source = inputs_and_outputs()[DRIVER][1]
        self.assertNotIn("gpr_claim", source)
        self.assertNotIn("ioremap(res->start", source)
        probe = definition(source, "static int gpueb_probe(")
        self.assertIn("mt6878_gpueb_adopt_window(s->rproc->dev.parent", probe)
        self.assertLess(probe.index("mt6878_gpueb_adoption_io_gate("), probe.index("rproc_boot("))
        release = definition(source, "static bool gpueb_release(")
        self.assertIn("mt6878_gpueb_unadopt_window(s->gpr_lease)", release)
        self.assertLess(release.index("s->boot_attempted && !s->boot_ref"),
                        release.index("mt6878_gpueb_unadopt_window("))

    def test_adopter_does_not_guess_hardware_boot(self):
        code = (ADOPTION / "mt6878-gpueb-adoption.c").read_text()
        self.assertIn('IORESOURCE_MEM, "gpueb_base"', code)
        self.assertIn("adopted->device != parent", code)
        for forbidden in ("request_mem_region(", "ioremap(", "readl(", "writel(",
                          "rproc_boot(", "request_firmware(", "dev_set_drvdata("):
            self.assertNotIn(forbidden, code)
        self.assertIn("return ret ? ret : -EOPNOTSUPP", code)
        self.assertIn("if (parent->clients)", code)

    def test_native_and_object_runners_refuse_local(self):
        env = dict(os.environ, CI="false", CC="/nonexistent/compiler")
        for script in (HERE / "run_gpueb_sram_adoption_ci.sh", ADOPTION / "smoke-kernel-ci.sh"):
            result = subprocess.run(["sh", str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("CI-only", result.stderr)
            self.assertEqual(subprocess.run(["sh", "-n", str(script)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
