#!/usr/bin/env python3
"""Compose the frozen native MD image with exact1009; CI-only, no activation."""
import argparse
import json
from pathlib import Path

import importlib.util


def helper():
    path = Path(__file__).with_name("stage-gnss-tx-image.py")
    spec = importlib.util.spec_from_file_location("gnss_image", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def stage(tree, report, tx_report, include_tx=True):
    gnss = helper()
    tree = gnss.isolated(tree)
    for path in (report, tx_report):
        if gnss.isolated(path) != path.absolute() or path.exists() or path.is_symlink():
            raise ValueError("profile output already exists or is unsafe")
    if report.resolve() == tx_report.resolve():
        raise ValueError("profile outputs must be distinct")
    parent = gnss.parent_stage()
    evidence = tree / ".tetris-image-evidence"
    parent_report = evidence / "native-parent.json"
    candidate_report = evidence / "gnss-tx.json"
    if evidence.exists() or evidence.is_symlink():
        raise ValueError("image evidence already exists")
    native = parent.stage(tree, parent_report)
    tx = None
    revision = 188 if include_tx else 187
    if include_tx:
        tx = gnss.stage(tree, parent_report, candidate_report, opt_in=True, pkgrel=revision)
        native.update(profile=gnss.PROFILE + "-wakeup", kernel_package=tx["kernel_package"],
                      gnss_tx_patch=tx["patch"], gnss_tx_patch_sha512=tx["patch_sha512"],
                      gnss_activation_changed=False, shipping_activation=False)
        native["changes"][tx["patch"]] = gnss.digest((gnss.HERE / gnss.PATCH).read_bytes())
    else:
        native["profile"] = "native-md-first-off-wakeup-diagnostic"
    spec = importlib.util.spec_from_file_location("native_wakeup", Path(__file__).with_name("stage-native-wakeup-image.py"))
    wakeup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wakeup)
    wakeup.extend(parent, tree, native, revision)
    outputs = [(report, native)] + ([(tx_report, tx)] if tx is not None else [])
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    return native


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmaports", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tx-report", type=Path, required=True)
    parser.add_argument("--include-exact1009", action="store_true")
    args = parser.parse_args()
    print(json.dumps(stage(args.pmaports, args.report, args.tx_report, args.include_exact1009), indent=2))
