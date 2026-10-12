#!/usr/bin/env python3
"""Typed DT fixtures and pinned source comparison; no local DT compilation."""
import copy
from pathlib import Path
import re
import subprocess
import unittest

import check


def ints(values):
    return b"".join(x.to_bytes(4, "big") for x in values)


def fixture():
    normal = {
        "/": {"compatible": b"nothing,tetris\0mediatek,mt6878\0", "model": b"Nothing CMF Phone 1\0"},
        "/chosen": {},
        check.SOC: {"#address-cells": ints([1]), "#size-cells": ints([1])},
        check.IFR: {"compatible": b"mediatek,mt6878-infracfg-ao\0syscon\0",
                    "reg": ints([0x10001000, 0x1000]), "phandle": ints([42])},
        "/modem": {"compatible": b"mediatek,mddriver\0", "status": b"disabled\0"},
        "/display": {"status": b"okay\0", "clocks": ints([7, 19])},
        "/topckgen": {"phandle": ints([7]), "#clock-cells": ints([1])},
    }
    dt = copy.deepcopy(normal)
    dt["/"]["model"] = check.MODEL
    dt["/chosen"][check.MARKER] = b""
    dt[check.IFR]["#clock-cells"] = ints([1])
    for node, memory in check.MEMORY.items():
        dt[node] = {"compatible": b"".join(c + b"\0" for c in check.COMPAT[node]),
                    "reg": ints(memory), "status": b"okay\0"}
        if node not in check.CLOCKS:
            continue
        ids, names = check.CLOCKS[node]
        dt[node]["clocks"] = ints([c for i in ids for c in (42, i)])
        dt[node]["clock-names"] = b"".join(n.encode() + b"\0" for n in names)
        irqs = [228, 229] if "ccif@" in node else [238, 259]
        dt[node]["interrupts"] = ints([c for i in irqs for c in (0, i, 4, 0)])
        for key, value in check.EXTRA[node].items():
            dt[node][key] = ints([value])
        if "dpmaif@" in node:
            dt[node]["dpmaif-infracfg"] = ints([42])
    return normal, dt


class HifDT(unittest.TestCase):
    def test_exact_resource_binding(self):
        normal, dt = fixture()
        check.validate_trees(normal, dt)

    def test_rejects_unrelated_changes_and_activation(self):
        for node, prop, value in [("/display", "status", b"disabled\0"),
                                  ("/modem", "status", b"okay\0"),
                                  ("/modem", "reg", ints([0xd180000, 0x2000])),
                                  (check.IFR, "reg", ints([0x1020e000, 0x1000]))]:
            normal, dt = fixture()
            dt[node][prop] = value
            with self.subTest(node=node, prop=prop), self.assertRaises(ValueError):
                check.validate_trees(normal, dt)

    def test_rejects_wrong_resources_and_unsafe_managed_properties(self):
        for prop, value in [("reg", ints([0x10209000, 0x2000, 0x1020a000, 0x1000])),
                            ("clocks", ints([7, 3])), ("interrupts", ints([0, 228, 8, 0, 0, 229, 4, 0])),
                            ("clock-names", b"guessed\0"), ("power-domains", ints([7, 0])),
                            ("assigned-clocks", ints([42, 3])), ("iommus", ints([7, 0]))]:
            normal, dt = fixture()
            dt[check.SOC + "/ccif@10209000"][prop] = value
            with self.subTest(prop=prop), self.assertRaises(ValueError):
                check.validate_trees(normal, dt)

    def test_rejects_missing_ambiguous_or_extra_nodes(self):
        for change in ("missing", "extra", "duplicate"):
            normal, dt = fixture()
            if change == "missing":
                dt.pop(check.SOC + "/ccif@1025d000")
            else:
                dt[check.SOC + "/unreviewed@1025d000"] = copy.deepcopy(dt[check.SOC + "/ccif@1025d000"])
            with self.subTest(change=change), self.assertRaises(ValueError):
                check.validate_trees(normal, dt)

    def test_phandle_numbers_are_not_hardware_identity(self):
        normal, dt = fixture()
        dt[check.IFR]["phandle"] = ints([53])
        for node, (ids, _) in check.CLOCKS.items():
            dt[node]["clocks"] = ints([c for i in ids for c in (53, i)])
        dt[check.SOC + "/dpmaif@10014000"]["dpmaif-infracfg"] = ints([53])
        check.validate_trees(normal, dt)

    def test_pinned_b41_ranges_irqs_and_clock_names(self):
        root = check.HERE.parents[3]
        vendor = root.parent / "android_kernel_device_modules_6.1_nothing_mt6878"
        if not vendor.exists():
            self.skipTest("exact vendor input not available; compiled DT checks remain mandatory")
        source = subprocess.check_output(["git", "-C", str(vendor), "show",
            "ee2be53cb75670b548948636a0db1d1ff112bf12:arch/arm64/boot/dts/mediatek/mt6878.dts"], text=True)
        for node, memory in check.MEMORY.items():
            comp = check.COMPAT[node][0].decode()
            marker = 'compatible = "' + comp + '";'
            self.assertEqual(source.count(marker), 1)
            body = source.split(marker, 1)[1].split("\n\t\t};", 1)[0]
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            data = re.search(r"\breg\s*=\s*(.*?);", body, re.S)[1]
            vendor_cells = [int(n, 0) for n in re.findall(r"0x[\da-fA-F]+|\b\d+\b", data)]
            self.assertEqual(vendor_cells, [c for start, size in zip(memory[::2], memory[1::2])
                                            for c in (0, start, 0, size)])
            if node in check.CLOCKS:
                names = re.search(r"clock-names\s*=\s*(.*?);", body, re.S)[1]
                self.assertEqual(re.findall(r'"([^"]+)"', names), check.CLOCKS[node][1])
                irq = re.search(r"interrupts\s*=\s*(.*?);", body, re.S)[1]
                actual = [int(n) for n in re.findall(r"GIC_SPI\s+(\d+)\s+IRQ_TYPE_LEVEL_HIGH\s+0", irq)]
                self.assertEqual(actual, [228, 229] if "ccif@" in node else [238, 259])


if __name__ == "__main__":
    unittest.main()
