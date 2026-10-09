#!/usr/bin/env python3
"""Actual pinned helper/stack checks; native fixture is emitted for CI only."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import test_lna_metadata_patch as metadata

HERE, MODULES, MODULE_PIN, PLAT = metadata.HERE, metadata.MODULES, metadata.MODULE_PIN, metadata.PLAT
apply_patch, source = metadata.apply_patch, metadata.source

GATE = HERE / "0003-gps-refuse-unproven-lna-control.patch"


def helper(text):
    start = text.index("void gps_dl_lna_pin_ctrl(")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def gated(text):
    with tempfile.TemporaryDirectory(prefix="gnss-lna-gate-") as directory:
        dest = Path(directory) / PLAT
        dest.parent.mkdir(parents=True)
        dest.write_text(text)
        apply_patch(directory, GATE, allow_offset=True)
        return dest.read_text()


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        metadata.MetadataTests.setUpClass()
        cls.pristine = gated(metadata.MetadataTests.fixed[PLAT])
        cls.stacked = gated(metadata.MetadataTests.stacked[PLAT])

    def test_independent_and_full_stack(self):
        self.assertEqual(helper(self.pristine), helper(self.stacked))
        self.assertIn("gps_dl_lna_metadata_init(&pdev->dev);", self.stacked)
        self.assertIn("gps_dl_lna_metadata_reset();", self.stacked)
        self.assertIn("static void gps_dl_remove", self.stacked)

    def test_packaged_metadata_matches_frozen_candidate(self):
        packaged = metadata.PACKAGE / "1006-vendor-gnss-readonly-lna-metadata.patch.vendor"
        if not packaged.exists():
            self.skipTest("main has not packaged1006 in this checkout")
        # If packaged, prove the exact hunks, not merely the candidate's name.
        candidate = (HERE / "0002-gps-mcudl-query-owned-lna-metadata.patch").read_text()
        self.assertEqual(packaged.read_text().split("--- a/", 1)[1],
                         candidate.split("--- a/", 1)[1])

    def test_no_state_or_metadata_can_authorize_control(self):
        body = helper(self.stacked)
        self.assertIn("ASSERT_LINK_ID(link_id, GDL_VOIDF());", body)
        self.assertIn("pr_warn_once", body)
        for token in ("pinctrl_select_state", "gpio_", "gpiod_", "of_",
                      "g_gps_dl_pinctrl", "gps_dl_get_lna_pin", "return 0"):
            self.assertNotIn(token, body)
        # The whole translation unit must no longer select any LNA state.
        self.assertNotIn("pinctrl_select_state", self.stacked)

    def test_active_tree_has_no_other_gpio_fallback(self):
        result = subprocess.run([
            "git", "-C", str(MODULES), "grep", "-n", "-E",
            r"(pinctrl_select_state|gpio_request[a-z_]*|gpio_direction[a-z_]*|gpio_set[a-z_]*|gpiod_[a-z_]+)[[:space:]]*\(",
            MODULE_PIN, "--", "connectivity/gps/data_link", "connectivity/gps/gps_mcudl",
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(PLAT + ":384:", lines[0])
        build = source(MODULES, MODULE_PIN, "connectivity/gps/data_link/plat/v051/Kbuild")
        self.assertIn("linux/gps_dl_linux_plat_drv.o", build)
        self.assertNotIn("gps_lna_drv.o", build)
        self.assertNotIn("gps_stp", build)

    def test_lifecycle_callers_still_route_to_gated_helper(self):
        power = source(MODULES, MODULE_PIN, "connectivity/gps/data_link/hal/gps_dl_power_ctrl.c")
        self.assertEqual(len(re.findall(r"gps_dl_lna_pin_ctrl\(", power)), 4)
        self.assertEqual(power.count("gps_dl_lna_pin_ctrl(link_id, true, false)"), 2)
        self.assertEqual(power.count("gps_dl_lna_pin_ctrl(link_id, false, false)"), 2)
        # Lookup/probe/remove lifecycle is untouched by the control candidate.
        before = metadata.MetadataTests.stacked[PLAT]
        self.assertEqual(before.replace(helper(before), "<helper>"),
                         self.stacked.replace(helper(self.stacked), "<helper>"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-control-fixture":
        GateTests.setUpClass()
        Path(sys.argv[2]).write_text(helper(GateTests.stacked))
    else:
        unittest.main()
