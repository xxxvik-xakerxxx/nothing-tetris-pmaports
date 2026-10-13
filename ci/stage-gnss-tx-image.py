#!/usr/bin/env python3
"""Explicit exact1009 extension of an isolated, frozen r184 CI package copy."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "patches/gnss/write-boundary"
PARENT_SHA256 = "12a98bc5ff8bf135c21fac95e9d30ae4cc0e26a63db00db1fdb6098da0d705c5"
MANIFEST_SHA256 = "a613bf4fb1bc8ac046fdbfead9963cc0166719959017768a59b30a6ab021d571"
PATCH = "1009-vendor-gnss-nonblocking-data-link-write.patch.vendor"
PATCH_SHA512 = (
    "6989187ef229f8c7fe91024ad56a2a90d04e51b4f230373ce072b329da619f281"
    "c172b56b29da83d192c697af0590662fdb697d8b5511aa7a30235bcc3ea6602"
)
PROFILE = "native-md-first-off-gnss-tx-exact1009-candidate"
CONFIG = "config-postmarketos-mediatek-mt6878.aarch64"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data, algorithm="sha256"):
    return hashlib.new(algorithm, data).hexdigest()


def parent_stage():
    path = ROOT / "ci/stage-native-modem-image.py"
    require(digest(path.read_bytes()) == PARENT_SHA256, "frozen r184 helper changed; re-review")
    spec = importlib.util.spec_from_file_location("gnss_tx_parent", path)
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    return parent


def inputs():
    raw = (HERE / "STAGING.json").read_bytes()
    require(digest(raw) == MANIFEST_SHA256, "exact1009 source manifest changed; re-review")
    manifest = json.loads(raw)
    data = (HERE / PATCH).read_bytes()
    require(digest(data, "sha512") == PATCH_SHA512 == manifest["patch_sha512"],
            "exact1009 patch hash changed")
    require(manifest["patch"] == "patches/gnss/write-boundary/" + PATCH and
            manifest["connectivity_commit"] == "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835",
            "wrong exact1009 source identity")
    return data, manifest


def isolated(path):
    resolved = path.resolve()
    root = ROOT.resolve()
    frozen = Path(os.environ.get("TETRIS_NATIVE_SOURCE_TREE", ROOT)).resolve()
    ci_copy = (os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true" and
               frozen != root and any(resolved == allowed or allowed in resolved.parents
                   for allowed in (root / "upstream/pmaports", root / "out")))
    for source in {root, frozen}:
        if source == root and ci_copy:
            continue
        require(not (resolved == source or source in resolved.parents or resolved in source.parents),
                "refusing to mutate repository/frozen source inputs")
    return resolved


def regular_input(tree, relative):
    path = tree / relative
    require(path.resolve() == path and path.is_file(), "missing or symlinked input: " + relative)
    return path.read_bytes()


def frozen_parent(parent):
    """Reconstruct the unchecksummed parent using its unchanged, pinned stager."""
    files = (parent.KERNEL + "/APKBUILD", parent.KERNEL + "/" + CONFIG,
             parent.DEVICE + "/APKBUILD", parent.DEVICE + "/deviceinfo",
             parent.DEVICE + "/boot_image.its")
    with tempfile.TemporaryDirectory(prefix="tetris-gnss-parent-") as directory:
        tree = Path(directory)
        for relative in files:
            path = tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(parent.frozen("pmaports/" + relative))
        metadata = parent.stage(tree, tree / "parent.json")
        files += tuple(parent.KERNEL + "/" + name for name in metadata["changes"])
        return metadata, {relative: (tree / relative).read_bytes() for relative in files}


def ordered_stack(apk, names):
    source = re.findall(r'^source="\n(.*?)^"\n', apk, re.M | re.S)
    prepare = re.findall(r'^prepare\(\) \{\n(.*?)^\}', apk, re.M | re.S)
    require(len(source) == len(prepare) == 1, "ambiguous source/prepare sections")
    listed = re.findall(r"^\t(100[1-9]-[^\s]+)$", source[0], re.M)
    applied = re.findall(r'< "\$srcdir"/(100[1-9]-[^\s]+)', prepare[0])
    require(listed == applied == list(names), "GNSS source/prepare prerequisite order changed")


def stage(tree, parent_report, report, opt_in=False, pkgrel=None):
    require(opt_in is True, "exact1009 requires explicit --include-exact1009 opt-in")
    require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true",
            "future candidate staging is GitHub CI-only")
    # r185 is already reserved by the separate native-rails extension.
    require(type(pkgrel) is int and pkgrel >= 186, "choose a distinct future candidate pkgrel >= 186")
    tree = isolated(tree)
    require(tree.is_dir(), "isolated pmaports COPY must already exist")
    report_path = Path(os.path.abspath(report))
    report = isolated(report_path)
    parent_path = Path(os.path.abspath(parent_report))
    require(report == report_path and parent_path.resolve() == parent_path,
            "reports must not traverse symlinks")
    require(tree in report.parents and tree in parent_path.parents and report != parent_path,
            "reports must be distinct files inside the isolated COPY")
    require(not report.exists() and not report.is_symlink(), "candidate report already exists")
    require(all(not path.exists() or path.is_dir() for path in report.parents),
            "candidate report parent is not a directory")
    parent = parent_stage()
    package = tree / parent.KERNEL
    require(package not in report.parents and tree / parent.DEVICE not in report.parents,
            "report overlaps package inputs")
    destination = package / PATCH
    require(isolated(destination) == destination and not destination.exists() and
            not destination.is_symlink(), "exact1009 output exists or escapes COPY")
    data, manifest = inputs()
    parent_raw = regular_input(tree, str(parent_path.relative_to(tree)))
    metadata = json.loads(parent_raw)
    expected, files = frozen_parent(parent)
    require(parent_raw == (json.dumps(expected, indent=2) + "\n").encode(),
            "requires exact frozen r184 diagnostic parent manifest")
    for relative, original in files.items():
        require(regular_input(tree, relative) == original,
                "frozen r184 package input changed: " + relative)
    apk_path = package / "APKBUILD"
    require(apk_path.stat().st_nlink == 1, "APKBUILD must be an independent COPY, not a hardlink")
    apk = files[parent.KERNEL + "/APKBUILD"].decode()
    require(PATCH not in apk, "exact1009 already staged")
    names = list(manifest["prerequisite_sha512"])
    ordered_stack(apk, names)
    for name, sha in manifest["prerequisite_sha512"].items():
        require(digest(regular_input(tree, parent.KERNEL + "/" + name), "sha512") == sha,
                "GNSS prerequisite hash changed: " + name)
    source_anchor = "\t" + names[-1] + "\n"
    prepare_anchor = ('\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                      '\t\t< "$srcdir"/' + names[-1] + '\n')
    apk = parent.change_once(apk, source_anchor, source_anchor + "\t" + PATCH + "\n")
    apk = parent.change_once(apk, prepare_anchor, prepare_anchor +
                             '\tpatch --fuzz=0 -p1 -d "$_connmods_dir" \\\n'
                             '\t\t< "$srcdir"/' + PATCH + '\n')
    apk = parent.change_once(apk, "pkgrel=184\n", f"pkgrel={pkgrel}\n")
    ordered_stack(apk, names + [PATCH])
    result = {
        "profile": PROFILE, "kernel_package": f"7.2.1-r{pkgrel}",
        "parent_manifest_sha256": digest(parent_raw), "parent": metadata,
        "parent_helper_sha256": PARENT_SHA256, "source_manifest_sha256": MANIFEST_SHA256,
        "patch": PATCH, "patch_sha512": PATCH_SHA512,
        "prerequisite_sha512": manifest["prerequisite_sha512"],
        "stacked_source_sha512": manifest["stacked_source_sha512"],
        "connectivity_commit": manifest["connectivity_commit"],
        "source_order": names + [PATCH], "prepare_order": names + [PATCH],
        "apkbuild_before_sha256": digest(files[parent.KERNEL + "/APKBUILD"]),
        "apkbuild_staged_sha256": digest(apk.encode()),
        "previous_module_closure_evidence": manifest["full_module_validation"],
        "validation": "static package staging only; candidate has not been built or executed",
        "matched_image_built": False, "phone_abi_compatible": False, "hardware_tested": False,
        "gnss_activation_changed": False, "shipping_activation": False,
        "end_user_radio_functionality": False, "modem_consumer_enabled": False,
        "checksums": "pending pmbootstrap checksum; recompute before prepare/build, never bypass",
        "next_gate": "build kernel and all external modules together in a fresh matched CI image",
        "residual_limits": manifest["residual_limits"],
    }
    # All source, order, profile and output checks precede candidate writes.
    destination.write_bytes(data)
    apk_path.write_text(apk)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmaports", type=Path, required=True)
    parser.add_argument("--parent-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--include-exact1009", action="store_true")
    parser.add_argument("--candidate-pkgrel", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.pmaports, args.parent_report, args.report,
                           args.include_exact1009, args.candidate_pkgrel), indent=2))


if __name__ == "__main__":
    main()
