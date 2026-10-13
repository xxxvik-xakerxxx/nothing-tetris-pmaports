#!/usr/bin/env python3
"""CI-only APK compatibility candidate; keep the frozen MD/GNSS composers intact.

Only the two reviewed 0f2b9b3e APK deltas are normalized, then restored after
composition. All validation/composition occurs in scratch before target writes.
This is static package preparation, not compilation or hardware certification.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

REVIEWED_SOURCE = "0f2b9b3e3eb894a15ef7fedb2266dd59f5726e04"
FROZEN_APK_SHA256 = "dd7688a578ce9c30935bce8209cb7487e27d85bf5a1a1bc293ada4c2e6cc0c75"
REVIEWED_APK_SHA256 = "2718757012b6de31399b591cdc516ed74498603ec3dbf30bb9eb7bc26ee6b716"
HELPERS = {
    "stage-native-gnss-image.py": "6e8965e15593b6ff2dd4276031b1297826186d3fd40b96db8f28c384cd5501cf",
    "stage-native-modem-image.py": "12a98bc5ff8bf135c21fac95e9d30ae4cc0e26a63db00db1fdb6098da0d705c5",
    "stage-gnss-tx-image.py": "e2f192c12f4ab2d6d063d27d6fa4075aba5e12d7e95d3aa06e8bca32dc6d2801",
    "stage-native-wakeup-image.py": "1be06375b65be11a18f1240cc6636bc141c16c96d85bfc2ad5a330708ad98e23",
}
GPUEB = "0120-misc-tetris-gpueb-authenticated-ram-analysis.patch"
CAMERA = "0121-media-i2c-imx882-acquire-mclk-source.patch"
GPUEB_OLD_SHA512 = (
    "31390471ea0d2236801761d85341ba454ab48121701ce885203fe9968b6ce708fc"
    "3d14a33e56c2561f5ac2bda2aa571fd939aff576374c724cd45c2c36e260a4"
)
PATCHES = {
    GPUEB: (
        "9b511e9bc06e3247c2f28b14f6cde674b838ffef82c8272369bd357e67d6b6aee"
        "49c24bf22080e359c4f7635e118511f171372d27a992ebb667d31291df3bb27"
    ),
    CAMERA: (
        "ae657b00fdd9d12d988939ac4a9d2b64b2a5835e038b78c36227b7e3aebc62a439"
        "bfcfcd1c454903ca623533d94b12b82546ea5b74b7463f6585faca210e064c"
    ),
}
PROFILE_SUFFIX = "-reviewed-apk-0f2b9b3e-candidate"
EVIDENCE = ".tetris-image-evidence"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data, algorithm="sha256"):
    return hashlib.new(algorithm, data).hexdigest()


def module(path):
    spec = importlib.util.spec_from_file_location("gnss_candidate_composer", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def composer():
    for filename, expected in HELPERS.items():
        path = Path(__file__).with_name(filename)
        require(digest(path.read_bytes()) == expected,
                "composition helper changed; re-review: " + filename)
    return module(Path(__file__).with_name("stage-native-gnss-image.py"))


def restore_reviewed_deltas(apk, parent):
    """Exact changes, not a general checksum/source-list compatibility rule."""
    anchor = "\t0116-media-platform-mediatek-mt6878-seninf-phy-backend.patch\n"
    apk = parent.change_once(apk, anchor, anchor + "\t" + CAMERA + "\n")
    apk = parent.change_once(apk, 'sha512sums="\n',
                             'sha512sums="\n' + PATCHES[CAMERA] + "  " + CAMERA + "\n")
    return parent.change_once(apk, GPUEB_OLD_SHA512 + "  " + GPUEB + "\n",
                              PATCHES[GPUEB] + "  " + GPUEB + "\n")


def output_path(path, gnss, tree, package_dirs):
    absolute = Path(os.path.abspath(path))
    require(gnss.isolated(absolute) == absolute, "output traverses a symlink")
    require(not absolute.exists() and not absolute.is_symlink(), "profile output already exists")
    require(all(not p.exists() or p.is_dir() for p in absolute.parents),
            "output parent is not a directory")
    require(not any(absolute == p or p in absolute.parents for p in package_dirs),
            "profile output overlaps package/evidence inputs")
    require(absolute != tree, "profile output overlaps COPY")
    return absolute


def stage(tree, report, tx_report, include_tx=False):
    require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true",
            "candidate composition is GitHub CI-only")
    require(type(include_tx) is bool, "exact1009 selection must be boolean")
    compose = composer()
    gnss = compose.helper()
    parent = gnss.parent_stage()
    absolute = Path(os.path.abspath(tree))
    require(gnss.isolated(absolute) == absolute and absolute.is_dir(),
            "isolated COPY missing or traverses a symlink")
    tree = absolute
    package_dirs = (tree / parent.KERNEL, tree / parent.DEVICE, tree / EVIDENCE)
    report = output_path(report, gnss, tree, package_dirs)
    tx_report = output_path(tx_report, gnss, tree, package_dirs)
    require(report != tx_report and report not in tx_report.parents and tx_report not in report.parents,
            "profile outputs must be distinct and non-overlapping")
    evidence = tree / EVIDENCE
    require(not evidence.exists() and not evidence.is_symlink(), "image evidence already exists")
    reserved = [parent.KERNEL + "/" + name for name in (
        "0180-native-md-first-off.patch", "0181-native-camera-after-md.patch",
        "0182-native-md-first-off-board.patch", "0183-native-camera-header-parent.patch",
        "0184-native-modem-single-ack.patch", "0187-native-modem-wakeup-sleep-veto.patch", gnss.PATCH)]
    for relative in reserved:
        path = tree / relative
        require(gnss.isolated(path) == path and not path.exists() and not path.is_symlink(),
                "reserved composition output already exists or is unsafe: " + relative)

    base = (parent.KERNEL + "/APKBUILD", parent.KERNEL + "/" + gnss.CONFIG,
            parent.DEVICE + "/APKBUILD", parent.DEVICE + "/deviceinfo",
            parent.DEVICE + "/boot_image.its")
    originals = {}
    frozen = {}
    for relative in base:
        originals[relative] = gnss.regular_input(tree, relative)
        require((tree / relative).stat().st_nlink == 1,
                "package input must be an independent COPY: " + relative)
        frozen[relative] = parent.frozen("pmaports/" + relative)
    apk_relative = base[0]
    require(digest(frozen[apk_relative]) == FROZEN_APK_SHA256, "frozen APK identity changed")
    reviewed = restore_reviewed_deltas(frozen[apk_relative].decode(), parent).encode()
    require(digest(reviewed) == REVIEWED_APK_SHA256, "reviewed APK delta contract changed")
    require(originals[apk_relative] == reviewed, "APK differs beyond the exact two reviewed deltas")
    for relative in base[1:]:
        require(originals[relative] == frozen[relative], "non-APK frozen input changed: " + relative)
    patch_evidence = {}
    for name, expected in PATCHES.items():
        relative = parent.KERNEL + "/" + name
        data = gnss.regular_input(tree, relative)
        require(digest(data, "sha512") == expected, "reviewed patch hash changed: " + name)
        originals[relative] = data
        patch_evidence[name] = {"sha512": expected, "sha256": digest(data)}
    # Verify prerequisites even for the wakeup-only route. No permission to
    # extend this APK bridge to another GNSS stack or another patch identity.
    _, manifest = gnss.inputs()
    for name, expected in manifest["prerequisite_sha512"].items():
        relative = parent.KERNEL + "/" + name
        data = gnss.regular_input(tree, relative)
        require(digest(data, "sha512") == expected, "GNSS prerequisite hash changed: " + name)
        originals[relative] = data

    # Frozen helpers may write incrementally. Run all of them only on scratch,
    # then prepare every resulting byte and destination before publishing.
    with tempfile.TemporaryDirectory(prefix="tetris-gnss-apk-candidate-") as directory:
        scratch_root = Path(directory).resolve()
        scratch = scratch_root / "copy"
        for relative, data in originals.items():
            path = scratch / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(frozen[apk_relative] if relative == apk_relative else data)
        scratch_report = scratch_root / "native.json"
        scratch_tx_report = scratch_root / "tx.json"
        native = compose.stage(scratch, scratch_report, scratch_tx_report, include_tx)
        normalized_apk = (scratch / apk_relative).read_bytes()
        final_apk = restore_reviewed_deltas(normalized_apk.decode(), parent).encode()
        (scratch / apk_relative).write_bytes(final_apk)
        compatibility = {
            "reviewed_source_commit": REVIEWED_SOURCE, "frozen_source_commit": parent.SOURCE,
            "frozen_apk_sha256": FROZEN_APK_SHA256, "input_apk_sha256": digest(reviewed),
            "normalized_composed_apk_sha256": digest(normalized_apk),
            "restored_composed_apk_sha256": digest(final_apk),
            "deltas": {GPUEB: "checksum replacement only", CAMERA: "source and checksum addition only"},
            "patches": patch_evidence, "composition_helpers_sha256": HELPERS,
            "internal_evidence": "unchanged normalized r184/exact1009 composition proofs",
            "validation": "static candidate composition only; not built or hardware tested",
        }
        native["profile"] += PROFILE_SUFFIX
        native["apk_candidate_compatibility"] = compatibility
        native["changes"].update({name: data["sha256"] for name, data in patch_evidence.items()})
        allowed = set(base) | set(reserved[:-1]) | {EVIDENCE + "/native-parent.json"}
        if include_tx:
            allowed |= {reserved[-1], EVIDENCE + "/gnss-tx.json"}
        plan = {}
        for path in scratch.rglob("*"):
            if not path.is_file():
                continue
            relative = str(path.relative_to(scratch))
            data = path.read_bytes()
            if data != originals.get(relative):
                require(relative in allowed, "unexpected composer output: " + relative)
                plan[tree / relative] = data
        plan[report] = (json.dumps(native, indent=2) + "\n").encode()
        if include_tx:
            tx = json.loads(scratch_tx_report.read_bytes())
            tx["profile"] += PROFILE_SUFFIX
            tx["apk_candidate_compatibility"] = compatibility
            plan[tx_report] = (json.dumps(tx, indent=2) + "\n").encode()

    # Recheck the full read set and all destinations after scratch composition.
    # Validation errors never change target inputs; multi-file publication is
    # not filesystem-atomic against I/O failure or concurrent external writers.
    for relative, data in originals.items():
        require(gnss.regular_input(tree, relative) == data, "input changed during preparation: " + relative)
    require(not evidence.exists() and not evidence.is_symlink(), "image evidence appeared during preparation")
    for relative in reserved:
        path = tree / relative
        require(not path.exists() and not path.is_symlink(),
                "reserved output appeared during preparation: " + relative)
    for path in plan:
        require(gnss.isolated(path) == path, "prepared output traverses a symlink")
        require(all(not p.exists() or p.is_dir() for p in path.parents),
                "prepared output parent is not a directory")
        relative = str(path.relative_to(tree)) if tree in path.parents else None
        if relative in base:
            require(path.stat().st_nlink == 1, "prepared package output is a hardlink")
        else:
            require(not path.exists() and not path.is_symlink(), "prepared output already exists")
    # tx_report is reserved even when the explicit exact1009 flag is absent.
    output_path(tx_report, gnss, tree, package_dirs)
    for path, data in plan.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmaports", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tx-report", type=Path, required=True)
    parser.add_argument("--include-exact1009", action="store_true")
    args = parser.parse_args()
    print(json.dumps(stage(args.pmaports, args.report, args.tx_report, args.include_exact1009), indent=2))


if __name__ == "__main__":
    main()
