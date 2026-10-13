#!/usr/bin/env python3
"""Opt-in MT6363 rails on a COPY of the r184 native MD diagnostic profile."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "patches/modem/md-pmic-supplier"
PATCH_SHA = "459f5c85b0b8372ce8328d8825013fc692873be1b7f70342d9c5c2d20fc3a832"
PARENT_SHA = "12a98bc5ff8bf135c21fac95e9d30ae4cc0e26a63db00db1fdb6098da0d705c5"
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
CORE_HASHES = {
    "drivers/regulator/core.c": "e09274caf113bd6def035b5918ac2e48a7605cd320eb1bfc73c34dd6223e9122",
    "drivers/regulator/of_regulator.c": "b6feada4bfec5356ef8efe432dd49fc9e6ffc27b383220faa8535a3aaef8de8a",
}
DRIVER_PATCH = "0185-native-modem-rails.patch"
DT_PATCH = "0186-native-modem-rails-registration-dt.patch"
PREFIX = "arch/arm64/boot/dts/mediatek/"
HELPER = "drivers/regulator/mt6363-modem-regulator.h"
CHILDREN = {"vbuck1": ("mt6363_vbuck1", 300000),
            "vbuck2": ("mt6363_vbuck2", 300000),
            "vsram-modem": ("mt6363_vsram_modem", 400000)}
SUPPLIES = {"md-vmodem": ("vbuck2", 800000),
            "md-vsram": ("vsram-modem", 800000),
            "md-vdigrf": ("vbuck1", 700000)}
REGISTRATION = ("\t\t/* Diagnostic registration preserves inherited voltage. The DT bounds\n"
                "\t\t * still constrain subsequent real consumer requests.\n"
                "\t\t */\n"
                "\t\tconfig.init_data->constraints.apply_uV = false;\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def parent_stage():
    path = ROOT / "ci/stage-native-modem-image.py"
    require(digest(path.read_bytes()) == PARENT_SHA, "r184 parent helper changed; re-review")
    return module("rails_parent_stage", path)


def dt_checker():
    return module("rails_parent_dt", ROOT / "ci/check-native-modem-image-dt.py")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def inputs():
    manifest = json.loads((HERE / "STAGING.json").read_text())
    evidence = json.loads((HERE / "SOURCE-EVIDENCE.json").read_text())
    patch = (HERE / "native-modem-rails.patch").read_bytes()
    require(digest(patch) == PATCH_SHA == manifest["patch"]["sha256"],
            "verified native rail patch identity changed")
    require(manifest["pins"] == evidence["pins"] == {"linux": LINUX, "vendor": VENDOR},
            "wrong native rail source pins")
    require(manifest["stock_consumer_mapping"] == {
        name: {"rail": rail, "microvolt": voltage} for name, (rail, voltage) in SUPPLIES.items()},
        "source-backed modem mapping changed")
    for path in (HELPER, PREFIX + "mt6878-modem-pmic-disabled.dtsi"):
        require(digest((HERE / Path(path).name).read_bytes()) == manifest["staged_after_sha256"][path],
                "canonical native input changed: " + path)
    return patch, manifest, evidence


def board_source(parent):
    return (parent.frozen("patches/modem/drafts/runtime-hif-dt/"
                          "mt6878-nothing-tetris-ccci-hif-resources.dts").decode() + parent.SUPPLIER_DTS)


def integration_patch(activate=False):
    inputs()
    parent = parent_stage()
    board = board_source(parent)
    extra = '\n#include "mt6878-modem-pmic-disabled.dtsi"\n\n&mddriver {\n'
    extra += '\tstatus = "disabled";\n\tccci-topckgen = <&topckgen>;\n'
    for name, (rail, voltage) in SUPPLIES.items():
        extra += f"\t{name}-supply = <&{CHILDREN[rail][0]}>;\n"
        extra += f"\t{name} = <{voltage} {voltage}>;\n"
    extra += "};\n"
    if activate:
        for label, _ in CHILDREN.values():
            extra += f'\n&{label} {{\n\tstatus = "okay";\n}};\n'
    header = (HERE / Path(HELPER).name).read_text()
    anchor = "\t\trdev = devm_regulator_register(dev, &states[i].desc, &config);\n"
    revised = parent.change_once(header, anchor, REGISTRATION + anchor)
    result = ("From: Tetris port maintainers\n"
              "Subject: [DIAGNOSTIC PATCH] MT6363: preserve inherited voltage at registration\n\n"
              "Keep the parsed DT ranges and real callbacks; suppress only core apply_uV.\n"
              "Modem remains disabled. Only explicit staging opt-in enables native children.\n\n")
    for path, before, after in ((HELPER, header, revised),
                               (PREFIX + parent.BOARD + ".dts", board, board + extra)):
        result += "diff --git a/" + path + " b/" + path + "\n"
        result += "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                              fromfile="a/" + path, tofile="b/" + path))
    return result.encode()


def apply(tree, data, check=False):
    result = subprocess.run(["git", "apply", "--verbose", "--whitespace=error"] +
                            (["--check"] if check else []) + ["-"],
                            cwd=tree, input=data, capture_output=True)
    require(result.returncode == 0 and b"Skipped patch" not in result.stderr,
            "native rail patch application failed: " + result.stderr.decode())


def check_kernel(kernel, activate=False):
    """Check the real prepared post-r184 sources, applying only to a temporary copy."""
    data, manifest, _ = inputs()
    parent = parent_stage()
    for path, expected in CORE_HASHES.items():
        require(digest((kernel / path).read_bytes()) == expected,
                "regulator core initialization changed; re-audit read-only registration: " + path)
    before = manifest["prepared_before_sha256"]
    for path, expected in before.items():
        require(digest((kernel / path).read_bytes()) == expected,
                "prepared native provider differs: " + path)
    for path in manifest["staged_after_sha256"].keys() - before.keys():
        require(not (kernel / path).exists(), "native extension already present: " + path)
    board = PREFIX + parent.BOARD + ".dts"
    require((kernel / board).read_text() == board_source(parent), "prepared r184 board differs")
    with tempfile.TemporaryDirectory(prefix="tetris-rails-check-") as directory:
        copy = Path(directory)
        for path in (*before, board):
            destination = copy / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((kernel / path).read_bytes())
        apply(copy, data, check=True)
        apply(copy, data)
        for path, expected in manifest["staged_after_sha256"].items():
            require(digest((copy / path).read_bytes()) == expected,
                    "verified patch output changed: " + path)
        followup = integration_patch(activate)
        apply(copy, followup, check=True)
        apply(copy, followup)
        require((copy / HELPER).read_text().replace(REGISTRATION, "", 1) ==
                (HERE / Path(HELPER).name).read_text(), "native callbacks changed")
    return {"native_patch_sha256": PATCH_SHA, "integration_patch_sha256": digest(followup)}


def typed(check, tree, owners, prop, value):
    if prop in {"ccci-topckgen", "dpmaif-infracfg"}:
        refs = check.cells(value)
        require(len(refs) == 1 and refs[0] in owners, "unresolved " + prop)
        return ((owners[refs[0]], ()),)
    return check.reference_value(tree, owners, prop, value)


def validate(normal, baseline, candidate, activate=False):
    """Validate the FULL shipping -> r184 -> rail board chain, including connectivity."""
    parent = dt_checker()
    parent.validate(normal, baseline)
    check = parent.hif
    owners, old_owners = check.phandle_owners(candidate), check.phandle_owners(baseline)
    require(set(old_owners.values()) == set(owners.values()) & set(baseline),
            "existing phandle ownership changed")
    pmics = [path for path, props in baseline.items()
             if check.compatible(props) == [b"mediatek,mt6363"]]
    require(len(pmics) == 1, "expected sole actual MT6363 PMIC")
    pmic = pmics[0]
    require(check.cells(baseline[pmic].get("reg", b"")) == [4, 0], "wrong MT6363 SPMI identity")
    regulators = pmic + "/regulators"
    require(check.compatible(baseline.get(regulators, {})) == [b"mediatek,mt6363-regulator"],
            "missing actual MT6363 regulator provider")
    for rail in ("vcn13", "vrfio18"):
        require(regulators + "/" + rail in baseline, "missing existing connectivity rail: " + rail)
    tops = [path for path, props in baseline.items()
            if check.compatible(props) == [b"mediatek,mt6878-topckgen", b"syscon"] and
            check.cells(props.get("reg", b"")) == [0x10000000, 0x1000]]
    require(len(tops) == 1, "expected actual MT6878 TOP syscon")
    added = {regulators + "/" + rail for rail in CHILDREN}
    require(set(candidate) == set(baseline) | added and not added & set(baseline),
            "unexpected native rail node inventory")
    status = b"okay\0" if activate else b"disabled\0"
    for rail, (label, minimum) in CHILDREN.items():
        props = candidate[regulators + "/" + rail]
        expected = {"status": status, "regulator-name": label.encode() + b"\0",
                    "regulator-min-microvolt": minimum.to_bytes(4, "big"),
                    "regulator-max-microvolt": (1193750).to_bytes(4, "big"),
                    "regulator-enable-ramp-delay": (180).to_bytes(4, "big"),
                    "regulator-allowed-modes": b"\0\0\0\0\0\0\0\x02"}
        require({k: v for k, v in props.items() if k not in {"phandle", "linux,phandle"}} == expected,
                "wrong native rail constraints/activation: " + rail)
    expected_md = {"ccci-topckgen": ((tops[0], ()),)}
    for name, (rail, voltage) in SUPPLIES.items():
        expected_md[name + "-supply"] = ((regulators + "/" + rail, ()),)
        expected_md[name] = voltage.to_bytes(4, "big") * 2
    require(not expected_md.keys() & baseline["/modem"].keys(), "baseline already has rail/TOP wiring")
    deltas = {}
    for path, props in baseline.items():
        for prop in props.keys() | candidate[path].keys():
            if prop in {"phandle", "linux,phandle"}:
                continue
            old, new = props.get(prop), candidate[path].get(prop)
            old = typed(check, baseline, old_owners, prop, old) if old is not None else None
            new = typed(check, candidate, owners, prop, new) if new is not None else None
            if old != new:
                deltas[path, prop] = new
    require(deltas == {("/modem", k): v for k, v in expected_md.items()},
            "unrelated baseline or native supply/TOP changed: " + repr(deltas))
    require(candidate["/modem"].get("status") == b"disabled\0", "modem must stay disabled")
    return {"pmic": pmic, "top": tops[0], "native_children_available": activate}


def isolated(path):
    path = path.resolve()
    sources = {ROOT.resolve(), Path(os.environ.get("TETRIS_NATIVE_SOURCE_TREE", ROOT)).resolve()}
    require(not any(path == root or root in path.parents for root in sources),
            "refusing to mutate repository/shipping inputs")
    return path


def stage(tree, parent_report, report, activate=False):
    require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true",
            "future diagnostic package staging is GitHub CI-only")
    tree, report = isolated(tree), isolated(report)
    parent_report = parent_report.resolve()
    require(tree in report.parents and tree in parent_report.parents and report != parent_report,
            "reports must be distinct files inside the isolated COPY")
    parent = parent_stage()
    package = tree / parent.KERNEL
    apk_path = package / "APKBUILD"
    config = package / "config-postmarketos-mediatek-mt6878.aarch64"
    for output in (apk_path, package / DRIVER_PATCH, package / DT_PATCH):
        resolved = isolated(output)
        require(tree in resolved.parents and resolved == output,
                "package output escapes COPY or is a symlink: " + str(output))
    require(report != apk_path and report != config and package not in report.parents and
            tree / parent.DEVICE not in report.parents, "report overlaps package inputs")
    apk = apk_path.read_text()
    require(DRIVER_PATCH not in apk and not (package / DRIVER_PATCH).exists() and
            not (package / DT_PATCH).exists() and not report.exists(), "rails already staged/output exists")
    metadata = json.loads(parent_report.read_text())
    require(metadata["profile"] == "native-md-first-off-diagnostic" and
            metadata["source_commit"] == parent.SOURCE and metadata["kernel_package"] == "7.2.1-r184" and
            metadata["board"] == parent.BOARD and metadata["fit_dtb"] == parent.BOARD + ".dtb" and
            metadata["required_uboot_commit"] == parent.UBOOT_SOURCE and
            metadata["device_package"] == "8-r20" and not metadata["sleep_idle_hotplug_allowed"] and
            not metadata["camera_gpu_enabled"] and not metadata["modem_consumer_enabled"],
            "requires exact staged r184 diagnostic parent")
    expected = dict(zip(("0180-native-md-first-off.patch", "0181-native-camera-after-md.patch"),
                        parent.INPUTS.values()))
    expected.update({"0182-native-md-first-off-board.patch": digest(parent.dt_patch().encode()),
                     "0183-native-camera-header-parent.patch": digest(parent.native_header_patch().encode()),
                     "0184-native-modem-single-ack.patch": digest(parent.modem_ack_patch().encode())})
    require(metadata["changes"] == expected, "parent snapshot manifest changed")
    for name, sha in expected.items():
        require(digest((package / name).read_bytes()) == sha and apk.count("\t" + name + "\n") == 1,
                "parent snapshot input differs: " + name)
    offsets = [apk.index("\t" + name + "\n") for name in expected]
    require(offsets == sorted(offsets), "parent postprofile patch ordering changed")
    patch_data, manifest, evidence = inputs()
    for record in manifest["packaged_inputs"]:
        require(digest((package / record["patch"]).read_bytes()) == record["sha256"],
                "existing connectivity/provider patch changed")
    cfg = config.read_text()
    require(parent.configured(cfg) == cfg, "parent diagnostic config changed")
    for symbol in ("MFD_MT6363", "REGULATOR_MT6363", "REGMAP_SPMI"):
        require(re.search(r"^CONFIG_" + symbol + r"=[ym]$", cfg, re.M), "missing native dependency: " + symbol)
    info = (tree / parent.DEVICE / "deviceinfo").read_text()
    fit = (tree / parent.DEVICE / "boot_image.its").read_text()
    require('deviceinfo_dtb="' + parent.BOARD + '"' in info and
            fit.count('data = /incbin/("' + parent.BOARD + '.dtb");') == 1,
            "parent DTB selection changed")
    extra = {DRIVER_PATCH: patch_data, DT_PATCH: integration_patch(activate)}
    anchor = "\t0184-native-modem-single-ack.patch\n"
    apk = parent.change_once(apk, anchor, anchor + "".join("\t" + name + "\n" for name in extra))
    apk = parent.change_once(apk, "pkgrel=184\n", "pkgrel=185\n")
    result = {"profile": "native-md-rails-diagnostic", "kernel_package": "7.2.1-r185",
              "parent_manifest_sha256": digest(parent_report.read_bytes()), "parent": metadata,
              "changes": {name: digest(data) for name, data in extra.items()},
              "pins": evidence["pins"], "native_kunit_runs": [38332592584, 38336059980],
              "board": parent.BOARD, "native_children_available": activate,
              "modem_consumer_enabled": False, "end_user_radio_functionality": False,
              "registration_policy": "apply_uV=false; parsed constraints and real callbacks retained",
              "registration_followup_native_validation": "not compiled or executed; static checks only",
              "hardware": "untested; no hardware or CI run performed by this helper",
              "checksums": "recompute with pmbootstrap checksum before building; do not bypass"}
    # Every input and output collision is checked before the first write.
    for name, data in extra.items():
        (package / name).write_bytes(data)
    apk_path.write_text(apk)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("stage", help="future CI only, on a disposable COPY of the parent")
    package.add_argument("--pmaports", type=Path, required=True)
    package.add_argument("--parent-report", type=Path, required=True)
    package.add_argument("--report", type=Path, required=True)
    kernel = commands.add_parser("check-kernel", help="static apply check; never modifies prepared sources")
    kernel.add_argument("prepared_kernel", type=Path)
    dt = commands.add_parser("check-dt", help="read-only validation of future CI-compiled DTBs")
    for name in ("native", "parent", "candidate"):
        dt.add_argument(name, type=Path)
    for command in (package, kernel, dt):
        command.add_argument("--activate-native-rails", action="store_true",
                             help="make only vbuck1/vbuck2/vsram-modem available; modem remains disabled")
    args = parser.parse_args()
    if args.command == "stage":
        result = stage(args.pmaports, args.parent_report, args.report, args.activate_native_rails)
    elif args.command == "check-kernel":
        result = check_kernel(args.prepared_kernel, args.activate_native_rails)
    else:
        check = dt_checker().hif
        result = validate(*(check.read_tree(path) for path in (args.native, args.parent, args.candidate)),
                          activate=args.activate_native_rails)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
