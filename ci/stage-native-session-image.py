#!/usr/bin/env python3
"""Opt-in1010 matched-image preparation above the frozen exact1009 route.

GitHub CI only. Accept a fresh reviewed package COPY, not an already composed
image. All composition/admission is prepared before target writes. No build,
dispatch, firmware/device access or hardware certification is performed here.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "patches/gnss/native-session"
PATCH = "1010-vendor-gnss-readonly-session-snapshot.patch.vendor"
PATCH_SHA512 = (
    "aced43779a9831047a8fa387063c45a5a3d8b14bf0112a7caf334d4b39caeedbd"
    "7335f2c057f647269e4ef8de93f98103ae2d29c25b4374e23454b0b9a3d40e6"
)
MANIFEST_SHA256 = "6d5d64de5e8d43e3635a30ecce3d5771838a84437385792fca9ed8516d1a6205"
HELPERS = {
    "stage-native-gnss-candidate-image.py": "8ba7633fa0521043527208c578af7c3f80e4ffadfaf81ef9d065759ac1999b99",
    "stage-native-gnss-image.py": "6e8965e15593b6ff2dd4276031b1297826186d3fd40b96db8f28c384cd5501cf",
    "stage-native-modem-image.py": "12a98bc5ff8bf135c21fac95e9d30ae4cc0e26a63db00db1fdb6098da0d705c5",
    "stage-gnss-tx-image.py": "e2f192c12f4ab2d6d063d27d6fa4075aba5e12d7e95d3aa06e8bca32dc6d2801",
    "stage-native-wakeup-image.py": "1be06375b65be11a18f1240cc6636bc141c16c96d85bfc2ad5a330708ad98e23",
    "select-native-modem-uboot.py": "0c24dbdc7e995f4146740472ffb46be58be5e62ff9ca21b9aac857c8725a7949",
}
PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
PROFILE_SUFFIX = "-session1010-candidate"
ARTIFACT = "nothing-tetris-native-md-gnss-session-images"
EVIDENCE = ".tetris-image-evidence"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data, algorithm="sha256"):
    return hashlib.new(algorithm, data).hexdigest()


def module(path):
    spec = importlib.util.spec_from_file_location("native_session_parent", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def regular(path):
    require(path.resolve() == path and path.is_file(), "missing or symlinked input: " + str(path))
    require(path.stat().st_nlink == 1, "input must be an independent COPY: " + str(path))
    return path.read_bytes()


def assets():
    readset = {}
    for name, expected in HELPERS.items():
        path = ROOT / "ci" / name
        raw = regular(path)
        require(digest(raw) == expected, "frozen helper/loader changed; re-review: " + name)
        readset[path] = raw
    raw = regular(SESSION / "STAGING.json")
    require(digest(raw) == MANIFEST_SHA256, "frozen session manifest changed; re-review")
    manifest = json.loads(raw)
    data = regular(SESSION / PATCH)
    require(manifest["connectivity_commit"] == PIN and manifest["patch"] == PATCH and
            digest(data, "sha512") == manifest["patch_sha512"] == PATCH_SHA512,
            "exact1010 patch/source identity changed")
    require(manifest["shipping_activation"] is False and manifest["compiled"] is False and
            manifest["hardware_tested"] is False, "session evidence is not the frozen draft")
    readset[SESSION / "STAGING.json"] = raw
    readset[SESSION / PATCH] = data
    for name, expected in manifest["frozen_api_sha256"].items():
        path = SESSION / name
        content = regular(path)
        require(digest(content) == expected, "frozen session API changed: " + name)
        readset[path] = content
    bridge = module(ROOT / "ci/stage-native-gnss-candidate-image.py")
    compose = bridge.composer()
    gnss = compose.helper()
    for path in (gnss.HERE / "STAGING.json", gnss.HERE / gnss.PATCH):
        readset[path] = regular(path)
    gnss.inputs()  # Exact1009 checks are unchanged, including all pinned hashes.
    return bridge, gnss, manifest, data, readset


def ordered_stack(apk, names):
    source = re.findall(r'^source="\n(.*?)^"\n', apk, re.M | re.S)
    prepare = re.findall(r'^prepare\(\) \{\n(.*?)^\}', apk, re.M | re.S)
    require(len(source) == len(prepare) == 1, "ambiguous source/prepare sections")
    pattern = r"((?:100[1-9]|1010)-[^\s]+)"
    listed = re.findall(r"^\t" + pattern + r"$", source[0], re.M)
    applied = re.findall(r'< "\$srcdir"/' + pattern, prepare[0])
    require(listed == applied == names, "session source/prepare order changed")


def extend(apk, parent, gnss, names, pkgrel):
    require(PATCH not in apk, "exact1010 already staged")
    ordered_stack(apk, names)
    require('"$_conn"/gps/data_link/plat/v051' in apk and
            '"$_connmods_dir"/connectivity/gps/data_link/plat/v051/gps_drv_dl_v051.ko' in apk,
            "expected actual packaged v051 build/install targets")
    source_anchor = "\t" + gnss.PATCH + "\n"
    prepare_anchor = ('\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                      '\t\t< "$srcdir"/' + gnss.PATCH + '\n')
    apk = parent.change_once(apk, source_anchor, source_anchor + "\t" + PATCH + "\n")
    apk = parent.change_once(apk, prepare_anchor, prepare_anchor +
                             '\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                             '\t\t< "$srcdir"/' + PATCH + '\n')
    apk = parent.change_once(apk, 'sha512sums="\n',
                             'sha512sums="\n' + PATCH_SHA512 + "  " + PATCH + "\n")
    apk = parent.change_once(apk, "pkgrel=188\n", f"pkgrel={pkgrel}\n")
    ordered_stack(apk, names + [PATCH])
    require(re.findall(r"^([0-9a-f]{128})  " + re.escape(PATCH) + r"$", apk, re.M) == [PATCH_SHA512],
            "exact1010 checksum row changed")
    return apk.encode()


def stage(tree, report, tx_report, session_report, opt_in=False, pkgrel=None):
    require(opt_in is True, "session1010 requires explicit --include-session1010 opt-in")
    require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true",
            "session candidate composition is GitHub CI-only")
    require(pkgrel is None or (type(pkgrel) is int and 188 < pkgrel <= 2147483647),
            "session candidate pkgrel must be an integer greater than r188")
    bridge, gnss, manifest, data, readset = assets()
    parent = gnss.parent_stage()
    tree = Path(os.path.abspath(tree))
    require(gnss.isolated(tree) == tree and tree.is_dir(), "isolated COPY missing or traverses a symlink")
    package_dirs = (tree / parent.KERNEL, tree / parent.DEVICE, tree / EVIDENCE)
    reports = [bridge.output_path(p, gnss, tree, package_dirs) for p in (report, tx_report, session_report)]
    for index, left in enumerate(reports):
        for right in reports[index + 1:]:
            require(left != right and left not in right.parents and right not in left.parents,
                    "profile outputs must be distinct and non-overlapping")
    report, tx_report, session_report = reports
    evidence = tree / EVIDENCE
    require(not evidence.exists() and not evidence.is_symlink(), "image evidence already exists")
    reserved = [parent.KERNEL + "/" + name for name in (
        "0180-native-md-first-off.patch", "0181-native-camera-after-md.patch",
        "0182-native-md-first-off-board.patch", "0183-native-camera-header-parent.patch",
        "0184-native-modem-single-ack.patch", "0187-native-modem-wakeup-sleep-veto.patch",
        gnss.PATCH, PATCH)]
    require(not list((tree / parent.KERNEL).glob("1010-*")), "1010 slot already reserved")
    for relative in reserved:
        path = tree / relative
        require(gnss.isolated(path) == path and not path.exists() and not path.is_symlink(),
                "reserved composition output already exists or is unsafe: " + relative)
    base = (parent.KERNEL + "/APKBUILD", parent.KERNEL + "/" + gnss.CONFIG,
            parent.DEVICE + "/APKBUILD", parent.DEVICE + "/deviceinfo", parent.DEVICE + "/boot_image.its")
    _, tx_manifest = gnss.inputs()
    names = list(tx_manifest["prerequisite_sha512"]) + [gnss.PATCH]
    inputs = list(base) + [parent.KERNEL + "/" + name for name in
                           (*bridge.PATCHES, *tx_manifest["prerequisite_sha512"])]
    originals = {relative: regular(tree / relative) for relative in inputs}
    readset.update({tree / relative: raw for relative, raw in originals.items()})

    # The frozen wrapper validates exact reviewed inputs and may write in stages.
    # It receives ONLY scratch; target publication starts after every late check.
    with tempfile.TemporaryDirectory(prefix="tetris-native-session-image-") as directory:
        root = Path(directory).resolve()
        scratch = root / "copy"
        for relative, raw in originals.items():
            path = scratch / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        native_path, tx_path = root / "native.json", root / "tx.json"
        native = bridge.stage(scratch, native_path, tx_path, include_tx=True)
        native_raw, tx_raw = native_path.read_bytes(), tx_path.read_bytes()
        require(json.loads(native_raw) == native and native["kernel_package"] == "7.2.1-r188" and
                native["profile"].endswith(bridge.PROFILE_SUFFIX), "expected frozen exact1009 r188 composition")
        require(json.loads(tx_raw)["kernel_package"] == "7.2.1-r188", "expected exact1009 source proof")
        revision = int(native["kernel_package"].rsplit("r", 1)[1]) + 1 if pkgrel is None else pkgrel
        apk_relative = base[0]
        before_apk = (scratch / apk_relative).read_bytes()
        final_apk = extend(before_apk.decode(), parent, gnss, names, revision)
        (scratch / apk_relative).write_bytes(final_apk)
        (scratch / parent.KERNEL / PATCH).write_bytes(data)
        session = {
            "profile": native["profile"] + PROFILE_SUFFIX, "artifact": ARTIFACT,
            "kernel_package": f"7.2.1-r{revision}",
            "parent_profile": native["profile"], "parent_kernel_package": native["kernel_package"],
            "parent_native_report_sha256": digest(native_raw), "parent_tx_report_sha256": digest(tx_raw),
            "composition_helpers_sha256": HELPERS, "source_manifest_sha256": MANIFEST_SHA256,
            "patch": PATCH, "patch_sha512": PATCH_SHA512, "connectivity_commit": PIN,
            "baseline_sha512": manifest["baseline_sha512"], "frozen_api_sha256": manifest["frozen_api_sha256"],
            "source_order": names + [PATCH], "prepare_order": names + [PATCH],
            "apkbuild_before_sha256": digest(before_apk), "apkbuild_staged_sha256": digest(final_apk),
            "module": "connectivity/gps/data_link/plat/v051/gps_drv_dl_v051.ko",
            "abi": "legacy plain-integer v051 retained; new ioctl31/version1/32-byte samples",
            "build_requirement": "package-matching compiler/config; full kernel/modules, connadp, conninfra, v051 with strict real-export modpost, boot/FIT/rootfs together",
            "checksums": "actual1010 row verified; pmbootstrap checksum still required for all generated composition inputs; never SKIP",
            "validation": "static composition only; not a compiled matching image or installed-module ABI proof",
            "matched_image_built": False, "phone_abi_compatible": False, "hardware_tested": False,
            "shipping_activation": False, "gnss_activation_changed": False,
            "end_user_radio_functionality": False, "navigation_validated": False,
            "normal_close_validated": False, "physical_stop_validated": False,
        }
        session_raw = (json.dumps(session, indent=2) + "\n").encode()
        native.update(profile=session["profile"], kernel_package=session["kernel_package"],
                      artifact=ARTIFACT, native_session=session)
        native["changes"][PATCH] = digest(data)
        proofs = {EVIDENCE + "/native-session-parent.json": native_raw,
                  EVIDENCE + "/gnss-session.json": session_raw}
        for relative, raw in proofs.items():
            (scratch / relative).write_bytes(raw)
        allowed = set(base) | set(reserved) | {
            EVIDENCE + "/native-parent.json", EVIDENCE + "/gnss-tx.json", *proofs}
        files = allowed | set(originals)
        directories = {str(p) for relative in files for p in Path(relative).parents if str(p) != "."}
        plan = {}
        for path in scratch.rglob("*"):
            relative = str(path.relative_to(scratch))
            require(not path.is_symlink(), "unexpected composer symlink: " + relative)
            if path.is_dir():
                require(relative in directories, "unexpected composer directory: " + relative)
                continue
            require(path.is_file() and relative in files, "unexpected composer output: " + relative)
            raw = path.read_bytes()
            if relative in originals and relative not in base:
                require(raw == originals[relative], "composer changed a retained input: " + relative)
            if raw != originals.get(relative):
                require(relative in allowed, "unexpected composer delta: " + relative)
                plan[tree / relative] = raw
        require(set(reserved) <= {str(p.relative_to(tree)) for p in plan}, "missing required composition output")
        plan[report] = (json.dumps(native, indent=2) + "\n").encode()
        plan[tx_report] = tx_raw  # Historical exact1009 proof, not a new-module claim.
        plan[session_report] = session_raw

    # All reads, reports, reservations and prepared outputs are re-admitted.
    # Fail-before-write validation is not multi-file filesystem atomicity under
    # I/O failure or concurrent external writes during publication.
    for path, raw in readset.items():
        require(regular(path) == raw, "input changed during preparation: " + str(path))
    require(not evidence.exists() and not evidence.is_symlink(), "image evidence appeared during preparation")
    require(not list((tree / parent.KERNEL).glob("1010-*")), "1010 slot appeared during preparation")
    for relative in reserved:
        path = tree / relative
        require(not path.exists() and not path.is_symlink(), "reserved output appeared during preparation: " + relative)
    for path in reports:
        bridge.output_path(path, gnss, tree, package_dirs)
    for path in plan:
        require(gnss.isolated(path) == path, "prepared output traverses a symlink")
        require(all(not p.exists() or p.is_dir() for p in path.parents), "prepared output parent is not a directory")
        if path not in {tree / relative for relative in base}:
            require(not path.exists() and not path.is_symlink(), "prepared output already exists")
    for path, raw in plan.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmaports", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tx-report", type=Path, required=True)
    parser.add_argument("--session-report", type=Path, required=True)
    parser.add_argument("--include-session1010", action="store_true")
    parser.add_argument("--candidate-pkgrel", type=int,
                        help="distinct revision >188; default derives r189 from frozen r188")
    args = parser.parse_args()
    print(json.dumps(stage(args.pmaports, args.report, args.tx_report, args.session_report,
                           args.include_session1010, args.candidate_pkgrel), indent=2))


if __name__ == "__main__":
    main()
