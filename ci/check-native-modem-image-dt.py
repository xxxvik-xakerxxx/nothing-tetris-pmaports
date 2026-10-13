#!/usr/bin/env python3
"""Validate the entire diagnostic board delta before packaging a boot image."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("hif_dt", ROOT / "patches/modem/drafts/runtime-hif-dt/check.py")
hif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hif)
from check_preflight_dt import cells, compatible, phandle_owners, reference_value, require, read_tree

NEMI = "/soc@0/syscon@10270000"
SPM = "/soc@0/syscon@1c001000"
SUPPLIER = SPM + "/power-controller-modem"
DOMAIN = SUPPLIER + "/power-domain@0"
MARKERS = ("tetris,modem-native-on-adoption-diagnostic", "tetris,modem-first-off-diagnostic")


def validate(normal, candidate):
    require(set(candidate) - set(normal) == set(hif.MEMORY) | {NEMI, SUPPLIER, DOMAIN},
            "unexpected native MD diagnostic node inventory")
    p = candidate[NEMI]
    require(set(p) - {"phandle", "linux,phandle"} == {"compatible", "reg", "status"} and
            compatible(p) == [b"mediatek,mt6878-nemicfg_ao_mem_reg_bus", b"syscon"] and
            cells(p["reg"]) == [0x10270000, 0x1000] and p["status"] == b"disabled\0",
            "NEMI must be the exact disabled syscon, not an enabled clock/device")
    p = candidate[SUPPLIER]
    require(set(p) - {"phandle", "linux,phandle"} ==
            {"compatible", "#address-cells", "#size-cells", "#power-domain-cells", "access-controllers", "status"},
            "native supplier gained unexpected resources or inherited final markers")
    require(compatible(p) == [b"mediatek,mt6878-modem-power-controller"] and
            p["status"] == b"disabled\0" and cells(p["#address-cells"]) == [1] and
            cells(p["#size-cells"]) == [0] and cells(p["#power-domain-cells"]) == [1],
            "wrong supplier identity/cell geometry/input activation")
    require(reference_value(candidate, phandle_owners(candidate), "access-controllers", p["access-controllers"]) ==
            ((hif.IFR, ()), (NEMI, ())), "wrong supplier bus-protection owners/order")
    p = candidate[DOMAIN]
    require(set(p) - {"phandle", "linux,phandle"} == {"reg", "#power-domain-cells", "status"} and
            cells(p["reg"]) == [0] and cells(p["#power-domain-cells"]) == [0] and
            p["status"] == b"disabled\0", "only disabled domain0 may be published by U-Boot")
    # The remaining tree must be byte/typed-reference identical to the already
    # verified HIF-only board, including display, SCP, USB and disabled modem.
    reduced = {path: dict(props) for path, props in candidate.items() if path not in {NEMI, SUPPLIER, DOMAIN}}
    for marker in MARKERS:
        require(reduced["/chosen"].pop(marker, None) == b"", "missing/nonempty diagnostic intent")
    hif.validate_trees(normal, reduced)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("diagnostic", type=Path)
    args = parser.parse_args()
    validate(read_tree(args.native), read_tree(args.diagnostic))
    print("PASS: exact HIF plus disabled MD supplier/domain0; final activation belongs only to fresh U-Boot handoff")
