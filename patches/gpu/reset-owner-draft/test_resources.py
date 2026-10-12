#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Resource/source contract checks only: no C execution, MMIO or compilation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_native import definition
from test_gpueb_power import vendor

EVIDENCE = json.loads((HERE / "RESOURCE-CONTRACT.json").read_text())
DTB = None


def resources_from_dts(text):
    node = definition(text, "gpueb: gpueb@13c00000 {")
    names = re.findall(r'"([^"]+)"', node.split("reg-names =", 1)[1].split(";", 1)[0])
    rows = re.findall(r"<0 (0x[\da-f]+) 0 (0x[\da-f]+)>",
                      node.split("reg =", 1)[1].split(";", 1)[0])
    if len(names) != len(rows) or len(set(names)) != len(names):
        raise ValueError("resource names/rows disagree")
    return [(name, int(start, 16), int(size, 16))
            for name, (start, size) in zip(names, rows)]


def production_profile(code):
    header = (HERE.parent / "sram-owner/mt6878-gpueb-sram-core.h").read_text()
    constants = {name: int(value, 16) for name, value in
                 re.findall(r"#define (GPUEB_\w+) (0x[\da-f]+)ULL", header)}

    def value(expression):
        terms = expression.strip().split(" + ")
        return sum(constants[term] if term in constants else int(term, 0)
                   for term in terms)

    table = code.split("} gpueb_resources[] = {", 1)[1].split("};", 1)[0]
    rows = re.findall(r'\{ "([^"]+)", ([^,]+), ([^}]+) \}', table)
    return [(name, value(start), value(size)) for name, start, size in rows]


class Resources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (HERE / "mt6878-gpueb-reset.c").read_text()
        cls.dts = vendor("arch/arm64/boot/dts/mediatek/mt6878.dts")

    def test_exact_source_pins(self):
        self.assertEqual(EVIDENCE["source"]["commit"],
                         "ee2be53cb75670b548948636a0db1d1ff112bf12")
        for path, digest in EVIDENCE["source"]["files_sha256"].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256(vendor(path).encode()).hexdigest(), digest)
        self.assertFalse(EVIDENCE["dtb"]["release_verified"])

    def test_production_profile_matches_all_pinned_resources(self):
        expected = resources_from_dts(self.dts)
        self.assertEqual(len(expected), 8)
        self.assertEqual(production_profile(self.code), expected)
        for name, start, size in expected:
            for replacement in (start + 4, start - 4):
                mutant = self.dts.replace(f"0x{start:x}", f"0x{replacement:x}")
                with self.subTest(resource=name, replacement=replacement):
                    self.assertNotEqual(production_profile(self.code), resources_from_dts(mutant))

    def test_base_dtb_resource_evidence_matches_source(self):
        evidence = EVIDENCE["dtb"]
        cells = evidence["cells"]["reg"]
        rows = [cells[i:i + 4] for i in range(0, len(cells), 4)]
        actual = [(name, (hi << 32) | lo, (shi << 32) | slo)
                  for name, (hi, lo, shi, slo) in zip(evidence["strings"]["reg-names"], rows)]
        self.assertEqual(len(rows), 8)
        self.assertEqual(actual, resources_from_dts(self.dts))

    def test_gpr_data_aliases_and_disjoint_control_claims(self):
        rows = production_profile(self.code)
        whole, gpr, bank, data = rows[:4]
        self.assertEqual(gpr[1] + gpr[2], data[1])
        self.assertEqual(data[1] + data[2], whole[1] + whole[2])
        controls = rows[4:]
        self.assertEqual(len(controls), 4)
        for _, start, size in controls:
            self.assertEqual(size, 4)
            self.assertGreaterEqual(start, bank[1] + bank[2])
        sorted_controls = sorted(controls, key=lambda row: row[1])
        for left, right in zip(sorted_controls, sorted_controls[1:]):
            self.assertLessEqual(left[1] + left[2], right[1])
        self.assertIn("GPUEB_MBOX_CONTROL_FIRST = 4", self.code)
        self.assertIn("GPUEB_MBOX_CONTROL_COUNT = 4", self.code)

    def test_preflight_bounds_and_order_in_both_real_callers(self):
        validate = definition(self.code, "int mt6878_gpueb_reset_validate_resources(")
        for token in ("if (!parent || !parent->dev.of_node)",
                      "!of_device_is_available(parent->dev.of_node)",
                      '!of_device_is_compatible(parent->dev.of_node, "mediatek,gpueb")',
                      "return -ENODEV;", "resource_type(&parent->resource[i]) == IORESOURCE_MEM",
                      "count != ARRAY_SIZE(gpueb_resources)", "!resource ||",
                      "resource->start != gpueb_resources[i].start",
                      "resource->end != gpueb_resources[i].start + gpueb_resources[i].size - 1"):
            self.assertIn(token, validate)
        self.assertLess(validate.index("return -ENODEV;"), validate.index("parent->num_resources"))
        for token in ("resource_size(", "request_mem_region(", "ioremap(", "readl(", "writel("):
            self.assertNotIn(token, validate)
        prepare = definition(self.code, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        self.assertLess(prepare.index("mt6878_gpueb_reset_validate_resources(parent)"),
                        prepare.index("pm_runtime_get_if_in_use("))
        control = (HERE.parent / "bound-parent-draft/mt6878-gpueb-control.c").read_text()
        caller = definition(control, "int mt6878_gpueb_control_prepare(")
        self.assertLess(caller.index("mt6878_gpueb_reset_validate_resources(parent)"),
                        caller.index("mt6878_gpueb_sram_create("))
        self.assertLess(caller.index("mt6878_gpueb_reset_validate_resources(parent)"),
                        caller.index("mt6878_gpueb_mfg0_resume("))
        self.assertIn('#include "mt6878-gpueb-reset.h"', control)

    def test_claim_failure_unwinds_only_completed_claims_before_irq(self):
        prepare = definition(self.code, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        loop = prepare.split("for (i = 0; i < GPUEB_MBOX_CONTROL_COUNT; i++) {", 1)[1]
        self.assertLess(loop.index("request_mem_region(mbox->start"), loop.index("scope->mbox_claims++"))
        self.assertLess(loop.index("goto release_mbox;"), loop.index("scope->mbox_claims++"))
        self.assertLess(loop.index("scope->mbox_control[i] = mbox;"), loop.index("scope->mbox_claims++"))
        self.assertLess(loop.index("scope->mbox_claims++"), loop.index("ioremap("))
        self.assertLess(loop.index("scope->mbox_claims++"), loop.index("request_threaded_irq("))
        self.assertEqual(prepare.count("request_mem_region("), 2)  # one bank + four loop claims
        cleanup = prepare.split("release_mbox:\n", 1)[1]
        self.assertLess(cleanup.index("release_mailbox_resources(scope)"), cleanup.index("release_mem_region("))
        self.assertLess(cleanup.index("release_mem_region("), cleanup.index("mt6878_gpueb_sram_put_window("))
        release = definition(self.code, "static void release_mailbox_resources(")
        self.assertIn("while (scope->mbox_claims)", release)
        self.assertIn("unsigned int i = --scope->mbox_claims;", release)
        self.assertIn("resource = scope->mbox_control[i];", release)
        self.assertLess(release.index("iounmap(scope->mbox_maps[i])"), release.index("release_mem_region("))
        self.assertIn("release_mem_region(resource->start, resource_size(resource))", release)

    def test_quarantine_retains_new_claims_and_prepare_does_not_access_them(self):
        destroy = definition(self.code, "int mt6878_gpueb_reset_destroy(")
        self.assertLess(destroy.index("return ret ?: -EBUSY"), destroy.index("release_mailbox_resources(scope)"))
        self.assertLess(destroy.index("free_irq("), destroy.index("release_mailbox_resources(scope)"))
        prepare = definition(self.code, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        self.assertEqual(prepare.count("ioremap("), 2)  # four controls loop + reset bank
        self.assertIn("scope->mbox_maps[i] = ioremap(mbox->start, resource_size(mbox))", prepare)
        self.assertIn("ioremap(resource->start, resource_size(resource))", prepare)
        for token in ("readl(", "writel(", "enable_irq(", "IRQF_SHARED", "devm_"):
            self.assertNotIn(token, prepare)

    def test_source_cumulative_mailbox_layout_and_memory_requirements(self):
        node = definition(self.dts, "gpueb: gpueb@13c00000 {")
        occupied = 0
        for prop, width in (("send-table", 3), ("recv-table", 5)):
            rows = re.findall(r"<([^>]+)>", node.split(prop + " =", 1)[1].split(";", 1)[0])
            cells = [int(item, 0) for row in rows for item in row.split()]
            self.assertEqual(cells, EVIDENCE["dtb"]["cells"][prop])
            self.assertEqual(len(rows), 11)
            for index in range(0, len(cells), width):
                self.assertEqual(cells[index + 1], 0)
                occupied += cells[index + 2]
        self.assertEqual(occupied, 88)
        self.assertLessEqual(occupied, 160)
        self.assertEqual(EVIDENCE["dtb"]["cells"]["gpueb-mem-table"], [0, 0x4000, 1, 0x180000])
        self.assertEqual(EVIDENCE["dtb"]["mali_pwr_irq"], EVIDENCE["dtb"]["cells"]["interrupts"])

    def test_actual_base_dtb_using_readonly_fdtget(self):
        if DTB is None:
            self.skipTest("supply --dtb for read-only actual DTB verification")
        evidence = EVIDENCE["dtb"]
        data = DTB.read_bytes()
        self.assertEqual(len(data), evidence["bytes"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), evidence["sha256"])

        def get(mode, node, prop=None, flag="-t"):
            args = ["fdtget", flag, mode, str(DTB), node] if flag == "-t" else ["fdtget", flag, str(DTB), node]
            if prop is not None:
                args.append(prop)
            return subprocess.check_output(args, text=True).split()

        for prop, expected in evidence["strings"].items():
            with self.subTest(property=prop):
                self.assertEqual(get("s", evidence["node"], prop), expected)
        for prop, expected in evidence["cells"].items():
            with self.subTest(property=prop):
                self.assertEqual([int(cell, 16) for cell in get("x", evidence["node"], prop)], expected)
        props = get(None, evidence["node"], flag="-p")
        for prop in evidence["absent_gpueb_properties"]:
            self.assertNotIn(prop, props)
        self.assertEqual(get(None, "/reserved-memory", flag="-l"), evidence["reserved_memory_children"])
        controller = evidence["irq_controller"]
        for prop, key in (("phandle", "phandle"), ("#interrupt-cells", "interrupt_cells")):
            self.assertEqual([int(cell, 16) for cell in get("x", controller["node"], prop)], [controller[key]])
        self.assertEqual(get("s", controller["node"], "compatible"), [controller["compatible"]])
        self.assertEqual(get("x", "/", "interrupt-parent"), ["1"])
        mali_irqs = [int(cell, 16) for cell in get("x", "/soc/mali@13000000", "interrupts")]
        self.assertEqual(mali_irqs[-4:], evidence["mali_pwr_irq"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtb", type=Path)
    args = parser.parse_args()
    DTB = args.dtb
    unittest.main(argv=[sys.argv[0]])
