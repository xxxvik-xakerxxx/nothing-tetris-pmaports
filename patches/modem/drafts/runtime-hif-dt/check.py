#!/usr/bin/env python3
"""Check a compiled HIF binding DT against shipping DT, never activate hardware."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from check_preflight_dt import cells, compatible, phandle_owners, read_tree, reference_value, require

SOC = "/soc@0"
IFR = SOC + "/syscon@10001000"
MARKER = "tetris,ccci-hif-resources-diagnostic"
MODEL = b"Nothing CMF Phone 1 (CCCI HIF resource binding)\0"
MEMORY = {
    SOC + "/ccif@10209000": [0x10209000, 0x1000, 0x1020a000, 0x1000],
    SOC + "/dpmaif@10014000": [0x10014000, 0x1000, 0x1022d000, 0x1000,
                                0x1022c000, 0x1000, 0x1022e000, 0x1000],
    SOC + "/syscon@1020e000": [0x1020e000, 0x1000],
    SOC + "/ccif@1024d000": [0x1024d000, 0x1000],
    SOC + "/ccif@1025d000": [0x1025d000, 0x1000],
}
COMPAT = {
    SOC + "/ccif@10209000": [b"mediatek,ccci_ccif"],
    SOC + "/dpmaif@10014000": [b"mediatek,dpmaif"],
    SOC + "/syscon@1020e000": [b"mediatek,infracfg", b"syscon"],
    SOC + "/ccif@1024d000": [b"mediatek,md_ccif4"],
    SOC + "/ccif@1025d000": [b"mediatek,md_ccif5"],
}
CLOCKS = {
    SOC + "/ccif@10209000": ([3, 4, 1, 2, 11, 7],
        ["infra-ccif-ap", "infra-ccif-md", "infra-ccif1-ap", "infra-ccif1-md",
         "infra-ccif4-md", "infra-ccif5-md"]),
    SOC + "/dpmaif@10014000": ([10, 5, 12],
        ["infra-dpmaif-clk", "infra-dpmaif-blk-clk", "infra-dpmaif-rg-mmw-clk"]),
}
EXTRA = {
    SOC + "/ccif@10209000": {
        "mediatek,sram-size": 512, "mediatek,ccif-hw-reset-ver": 1,
        "mediatek,ccif-hw-reset-bit": 26},
    SOC + "/dpmaif@10014000": {
        "mediatek,dpmaif-ver": 3, "mediatek,dpmaif-cap": 4,
        "mediatek,plat-info": 6878, "hw-reset-ver": 1},
}


def validate_trees(normal, candidate):
    require(set(candidate) - set(normal) == set(MEMORY) and set(normal) <= set(candidate),
            "HIF experiment changes unexpected node inventory")
    require({b"nothing,tetris", b"mediatek,mt6878"} <= set(compatible(normal["/"])),
            "not the native Tetris tree")
    require(cells(normal[SOC]["#address-cells"]) == [1] and
            cells(normal[SOC]["#size-cells"]) == [1], "wrong native bus geometry")
    require(cells(normal[IFR]["reg"]) == [0x10001000, 0x1000] and
            compatible(normal[IFR]) == [b"mediatek,mt6878-infracfg-ao", b"syscon"],
            "wrong existing AO provider")
    owners, old_owners = phandle_owners(candidate), phandle_owners(normal)
    allowed = {("/", "model"): MODEL, ("/chosen", MARKER): b"",
               (IFR, "#clock-cells"): (1).to_bytes(4, "big")}
    deltas = {}
    for node, properties in normal.items():
        for key in properties.keys() | candidate[node].keys():
            if key in ("phandle", "linux,phandle"):
                continue
            before, after = properties.get(key), candidate[node].get(key)
            if before is not None and after is not None:
                before = reference_value(normal, old_owners, key, before)
                after = reference_value(candidate, owners, key, after)
            if before != after:
                deltas[node, key] = candidate[node].get(key)
    require(deltas == allowed, "shipping device properties changed: " + repr(deltas))
    for node, registers in MEMORY.items():
        p = candidate[node]
        expected_keys = {"compatible", "reg", "status"}
        if node in CLOCKS:
            expected_keys |= {"interrupts", "clocks", "clock-names"} | EXTRA[node].keys()
        if node.endswith("/dpmaif@10014000"):
            expected_keys.add("dpmaif-infracfg")
        require(set(p) - {"phandle", "linux,phandle"} == expected_keys,
                "unexpected HIF managed resources: " + node)
        require(compatible(p) == COMPAT[node] and cells(p["reg"]) == registers and
                p["status"] == b"okay\0", "wrong HIF identity/range/status: " + node)
        if node not in CLOCKS:
            continue
        ids, names = CLOCKS[node]
        clock_values = reference_value(candidate, owners, "clocks", p["clocks"])
        require(clock_values == tuple((IFR, (i,)) for i in ids), "wrong HIF clock owner/ID")
        require(p["clock-names"] == b"".join(n.encode() + b"\0" for n in names),
                "wrong HIF clock names/order")
        lines = [228, 229] if "ccif@" in node else [238, 259]
        require(cells(p["interrupts"]) == [c for irq in lines for c in (0, irq, 4, 0)],
                "wrong HIF SPI/trigger/geometry")
        for key, value in EXTRA[node].items():
            require(cells(p[key]) == [value], "wrong MT6878 HIF capability")
        if "dpmaif-infracfg" in p:
            require(cells(p["dpmaif-infracfg"]) == [cells(candidate[IFR]["phandle"])[0]],
                    "DPMAIF reset must reference the actual AO provider")
    require(candidate.get("/modem", {}).get("status") == b"disabled\0" and
            not {"reg", "interrupts", "power-domains", "clocks"} & candidate["/modem"].keys(),
            "modem activation combined with HIF resource binding")
    return SOC + "/ccif@10209000"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normal", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    validate_trees(read_tree(args.normal), read_tree(args.candidate))
    print("PASS: native HIF DT resources and nine real CCF references; modem stays disabled")
