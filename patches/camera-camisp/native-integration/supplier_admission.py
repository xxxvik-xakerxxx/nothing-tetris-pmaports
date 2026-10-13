#!/usr/bin/env python3
"""Stage a read-only kernel admission guard over the frozen camera provider."""
import argparse
import difflib
import json
from pathlib import Path
import tempfile

import check
import generate as gen
import md_on_adoption as md

HERE = Path(__file__).resolve().parent
INC = gen.DEST + "mt6878-native-vmm.inc"
PATCH = HERE / "supplier-admission.patch"
REPORT = HERE / "supplier-admission-evidence.json"
OWNERS = ("mediatek,vmm_notifier", "mediatek,mtk-mmdvfs-v3")
SOURCE_HASHES = {
    "drivers/misc/mediatek/vmm/mtk-vmm-notifier.c":
        "8c67354ede2ada45b11d55a8f659f7450d170bd0b602155e2277a14ed81b336d",
    "drivers/soc/mediatek/mtk-mmdvfs-v3.c":
        "b523231cf75cae38ebad6e927f0e72f5b47b98fbc2befb7d03b4d0a4fe272d37",
}
CALL = """\t\tret = scpsys_vmm_admit_legacy_node(scpsys->dev, node);
\t\tif (ret) {
\t\t\tof_node_put(node);
\t\t\tgoto put_rails;
\t\t}
"""


def source_contract(vendor):
    for path, expected in SOURCE_HASHES.items():
        md.require(md.digest(vendor[path]) == expected, "exact B4.1 voter source required: " + path)
    notifier = vendor[next(iter(SOURCE_HASHES))].decode()
    firmware = vendor["drivers/soc/mediatek/mtk-mmdvfs-v3.c"].decode()
    opened = check.body(notifier, "vmm_locked_isp_open")
    md.require("mtk_mmdvfs_genpd_notify(VMM_USR_CAM,true);" in opened and
               "mtk_mmdvfs_camera_notify(true);" in opened, "camera votes without a rail handle")
    for name, token in (("mtk_mmdvfs_camera_notify", "FUNC_VMM_CEIL_ENABLE"),
                        ("mtk_mmdvfs_genpd_notify", "FUNC_VMM_GENPD_NOTIFY")):
        md.require("mmdvfs_vcp_ipi_send(" + token in check.body(firmware, name),
                   "source-backed firmware voter route: " + name)
    md.require('compatible = "' + OWNERS[0] + '"' in notifier and
               'compatible = "' + OWNERS[1] + '"' in firmware, "exact legacy driver matching")


def candidate(before, helper=None):
    helper = helper if helper is not None else (HERE / "mt6878-vmm-admission.c.inc").read_text()
    helper = gen.replace_once(helper, "/* SPDX-License-Identifier: GPL-2.0-only */\n", "")
    after = gen.replace_once(before, "static int scpsys_vmm_prepare(struct scpsys *scpsys)\n{",
                             helper + "\nstatic int scpsys_vmm_prepare(struct scpsys *scpsys)\n{")
    return gen.replace_once(after, "\t\tif (!of_device_is_available(node))\n\t\t\tcontinue;\n",
                             "\t\tif (!of_device_is_available(node))\n\t\t\tcontinue;\n" + CALL)


def contract(after, before):
    guard = check.body(after, "scpsys_vmm_admit_legacy_node")
    expected = (''.join('!of_device_is_compatible(node,"' + owner + '")&&' for owner in OWNERS)
                .removesuffix("&&") + ')return0;')
    md.require(guard.startswith("if(" + expected), "both independent firmware owners veto admission")
    md.require(guard.endswith("node);return-EBUSY;"), "legacy ownership is a hard busy error")
    md.require(guard == "if(" + expected + check.compact(
        'dev_err(dev, "%pOF: legacy VMM firmware voter blocks native supplier admission\\n", node);'
        'return -EBUSY;'), "admission guard only observes identity and returns an error")
    prepare = check.body(after, "scpsys_vmm_prepare")
    md.require("if(!of_device_is_available(node))continue;" + check.compact(CALL) +
               "for_each_property_of_node(node,prop)" in prepare,
               "available legacy owner rejected before supply scan; release node and both rails")
    md.require(prepare.index("scpsys_vmm_admit_legacy_node") < prepare.index("devm_kzalloc"),
               "veto before supplier construction")
    # Removing only this addition must recover the frozen kernel bytes exactly.
    helper = gen.function(after, "static int scpsys_vmm_admit_legacy_node(struct device *dev, struct device_node *node)\n")
    restored = gen.replace_once(after, helper + "\n\n", "")
    restored = gen.replace_once(restored, CALL, "")
    md.require(restored == before, "one bounded admission operation; all existing transitions preserved")
    md.require(after.index(helper) > after.index("#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)"),
               "guard remains inside default-off implementation")


def patch_text(before, after):
    return "diff --git a/" + INC + " b/" + INC + "\n" + "".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile="a/" + INC, tofile="b/" + INC))


def validate(archive=None, vendor_repo=None, modules_repo=None):
    overlay, report, files, _ = md.validate(gen, archive, vendor_repo, modules_repo)
    md.require(overlay == md.OVERLAY.read_text() and report == json.loads(md.REPORT.read_text()),
               "frozen MD/camera composition must match stored artifacts")
    vendor = gen.vendor_inputs(vendor_repo, modules_repo)
    source_contract(vendor)
    before = files[INC]
    evidence = json.loads((HERE / "evidence.json").read_text())
    md.require(md.digest(before.encode()) == evidence["payload_sha256"][INC],
               "canonical and MD-composed camera preimages must be identical")
    after = candidate(before)
    contract(after, before)
    text = patch_text(before, after)
    with tempfile.TemporaryDirectory(prefix=".vmm-admission-", dir=HERE) as directory:
        tree = Path(directory)
        for path, content in files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        md.apply_exact(tree, text, {INC: after})
        actual = {str(p.relative_to(tree)): p.read_text() for p in tree.rglob("*") if p.is_file()}
        md.require(actual == {**files, INC: after}, "only kernel admission code may change")
    result = dict(vendor_commit=gen.VENDOR, source_sha256=SOURCE_HASHES,
                  canonical_camera_sha256=report["canonical_camera_sha256"],
                  md_composition_report_sha256=report["report_sha256"],
                  kernel_preimage_sha256=md.digest(before.encode()),
                  kernel_output_sha256=md.digest(after.encode()), patch_sha256=md.digest(text.encode()),
                  rejected_owners=list(OWNERS), errno="-EBUSY",
                  activation="none; default n; no shipping or frozen provider artifacts changed",
                  validation="Python static contracts and exact kernel patch application only",
                  compiled=False, hardware_tested=False)
    return text, result, before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--vendor-repo", type=Path)
    parser.add_argument("--modules-repo", type=Path)
    args = parser.parse_args()
    text, report, _, _ = validate(args.kernel_archive, args.vendor_repo, args.modules_repo)
    serialized = json.dumps(report, indent=2) + "\n"
    if args.write:
        PATCH.write_text(text)
        REPORT.write_text(serialized)
    md.require(PATCH.read_text() == text and REPORT.read_text() == serialized, "admission sidecar drift")
    print("Legacy VMM firmware owner veto verified in actual kernel overlay; frozen provider preserved; no C execution")


if __name__ == "__main__":
    main()
