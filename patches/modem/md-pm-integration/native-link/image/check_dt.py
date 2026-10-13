#!/usr/bin/env python3
"""Read-only exact compiled candidate delta; status changes are never authorized."""
import argparse
import json
from pathlib import Path

import native_image_dt as dt

HIF = tuple("/soc@0/" + name for name in (
    "ccif@10209000", "dpmaif@10014000", "ccif@1024d000", "ccif@1025d000"))
SPM = "/soc@0/syscon@1c001000/power-controller-modem"


def typed(tree, owners, key, raw):
    if key in ("ccci-topckgen", "ccci-infracfg", "dpmaif-infracfg"):
        value = dt.cells(raw)
        dt.require(len(value) == 1 and value[0] in owners, "unresolved controller: " + key)
        return ((owners[value[0]], ()),)
    return dt.reference_value(tree, owners, key, raw)


def validate(baseline, candidate):
    dt.require(set(baseline) == set(candidate), "native START changes baseline node inventory")
    old, owners = dt.phandle_owners(baseline), dt.phandle_owners(candidate)
    expected = {("/modem", "reg"): bytes.fromhex("000000000d1800000000000000002000000000001c8030000000000000001000"),
        ("/modem", "interrupts"): b"".join(value.to_bytes(4, "big") for value in (0, 491, 4, 0, 0, 228, 4, 0, 0, 229, 4, 0)),
        ("/modem", "power-domains"): ((SPM, (0,)),),
        ("/modem", "mediatek,mdhif-type"): (6).to_bytes(4, "big"),
        ("/modem", "mediatek,cldma-capability"): (14).to_bytes(4, "big"),
        ("/modem", "mediatek,offset-epon-md1"): (0x64).to_bytes(4, "big") + (6).to_bytes(4, "big"),
        ("/modem", "mediatek,boot-status-config"): (1).to_bytes(4, "big"),
        ("/modem", "ccci-infracfg"): (("/soc@0/syscon@10001000", ()),)}
    expected.update({(path, "status"): b"disabled\0" for path in HIF})
    changes = {}
    for path, props in baseline.items():
        for key in props.keys() | candidate[path].keys():
            if key in ("phandle", "linux,phandle"):
                continue
            before, after = props.get(key), candidate[path].get(key)
            before = typed(baseline, old, key, before) if before is not None else None
            after = typed(candidate, owners, key, after) if after is not None else None
            if before != after:
                changes[path, key] = after
    dt.require(changes == expected, "unexpected compiled native DT delta; SCP/USB/conninfra/display must be unchanged: " + repr(changes))
    dt.require(candidate["/modem"].get("status") == b"disabled\0", "native consumer activation is not admitted")
    for name in ("md-vmodem-supply", "md-vsram-supply", "md-vdigrf-supply"):
        refs = dt.cells(candidate["/modem"].get(name, b""))
        dt.require(len(refs) == 1 and refs[0] in owners and
                   candidate[owners[refs[0]]].get("status") == b"disabled\0", "native rail activated/missing")
    return {"status": "passed", "scope": "compiled DT delta only; no loader/secure admission",
            "consumer": "disabled", "hif": "disabled", "rails": "disabled",
            "scp_usb_conninfra_display": "typed-reference-identical to inherited f25 image source baseline"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("fresh DT report required")
    try:
        result = validate(dt.read_tree(args.baseline), dt.read_tree(args.candidate))
    except Exception as error:
        args.report.write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise
    args.report.write_text(json.dumps(result, indent=2) + "\n")
