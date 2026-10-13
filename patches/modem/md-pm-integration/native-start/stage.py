#!/usr/bin/env python3
"""Generate/check additive native and real CCCI overlays, without compilation."""
import argparse
import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
UPSTREAM = REPO.parent
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
E = "drivers/misc/mediatek/eccci/"
P = "drivers/pmdomain/mediatek/"
API = "include/linux/soc/mediatek/mt6878_md_native_on.h"
FLAG = "IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)"


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def replace(text, old, new):
    require(text.count(old) == 1, "missing/ambiguous native-start anchor: " + repr(old[:100]))
    return text.replace(old, new, 1)


def patch(before, after):
    chunks = []
    for name, new in sorted(after.items()):
        old = before.get(name, "")
        if old == new:
            continue
        chunks.append(f"diff --git a/{name} b/{name}\n")
        if name not in before:
            chunks.append("new file mode 100644\n")
        chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile="a/" + name if name in before else "/dev/null", tofile="b/" + name))
    return "".join(chunks)


def native_candidate(before):
    after = dict(before)
    name = P + "mt6878-modem-real-boot.h"
    after[name] = replace(after[name], "\tstruct mt6878_md_adoption *owner;\n",
        "\tstruct mt6878_md_adoption *owner;\n\tstruct scpsys_domain *pd;\n")
    after[name] = replace(after[name], "\telse\n\t\towner->attached = get_device(dev);",
        "\telse {\n\t\towner->attached = get_device(dev);\n"
        "\t\tmt6878_md_real_boot_tail.pd = pd;\n\t}")
    require(after[name].endswith("\n#endif\n"), "real-ON header suffix differs")
    after[name] = after[name][:-len("#endif\n")] + '#include "native-on-provider.h"\n\n#endif\n'
    after[P + "native-on-provider.h"] = (HERE / "native-on-provider.h").read_text()
    after[P + "native-start.Kconfig"] = (HERE / "native-start.Kconfig").read_text()
    after[API] = (HERE / "mt6878_md_native_on.h").read_text()
    after[P + "Kconfig"] += '\nsource "drivers/pmdomain/mediatek/native-start.Kconfig"\n'
    return after


def vendor_candidate(before):
    after = dict(before)
    def edit(name, old, new):
        after[E + name] = replace(after[E + name], old, new)
    edit("Kconfig", "config MTK_ECCCI_TETRIS_OWNER\n",
         (HERE / "vendor-start.Kconfig").read_text() + "\nconfig MTK_ECCCI_TETRIS_OWNER\n")
    edit("Makefile", "ccci_md_all-$(CCCI_OBJ) += fsm/ccci_tetris_owner.o hif/ccci_tetris_hif_owned.o",
         "ifeq ($(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START), y)\n"
         "ccci_md_all-$(CCCI_OBJ) += fsm/ccci_tetris_native_start.o\nelse\n"
         "ccci_md_all-$(CCCI_OBJ) += fsm/ccci_tetris_owner.o hif/ccci_tetris_hif_owned.o\nendif")
    for name in ("fsm/modem_sys1.c", "fsm/ccci_fsm.c", "hif/ccci_hif_ccif.c", "hif/ccci_dpmaif_com.c"):
        # Kernel headers must define IS_ENABLED before this conditional.
        source = after[E + name]
        match = re.search(r'^#include <linux/[^\n]+>\n', source, re.M)
        require(match is not None, "missing leading kernel include: " + name)
        at = match.end()
        after[E + name] = source[:at] + '#if ' + FLAG + '\n#include "ccci_tetris_native_start.h"\n#endif\n' + source[at:]
    after[E + "fsm/ccci_tetris_native_start.c"] = (HERE / "ccci_tetris_native_start.c").read_text()
    after[E + "inc/ccci_tetris_native_start.h"] = (HERE / "ccci_tetris_native_start.h").read_text()
    after[E + "hif/native-hif-owner.h"] = (HERE / "native-hif-owner.h").read_text()
    edit("hif/ccci_hif.c", "struct ccci_hif_ops *ccci_hif_op[CCCI_HIF_NUM];",
         'struct ccci_hif_ops *ccci_hif_op[CCCI_HIF_NUM];\n#include "native-hif-owner.h"')
    edit("hif/ccci_hif.c", "\tif (hif_id < CCCI_HIF_NUM) {",
         "#if " + FLAG + "\n\t/* Native providers use the checked, sealed API only. */\n"
         '\tCCCI_ERROR_LOG(0, CORE, "native HIF rejects legacy registration\\n");\n'
         "\treturn;\n#endif\n\tif (hif_id < CCCI_HIF_NUM) {")
    edit("hif/ccci_hif_ccif.c", "\tret = ccci_ccif_hif_init(pdev, CCIF_HIF_ID);",
         "#if " + FLAG + "\n\tret = ccci_tetris_hif_claim(pdev, CCIF_HIF_ID);\n"
         "\tif (ret)\n\t\treturn ret;\n#endif\n\tret = ccci_ccif_hif_init(pdev, CCIF_HIF_ID);")
    edit("hif/ccci_hif_ccif.c", "\tccci_hif_register(ccif_ctrl->hif_id,\n\t\t(void *)ccci_ccif_ctrl, &ccci_hif_ccif_ops);",
         "#if " + FLAG + "\n\treturn ccci_tetris_hif_register(ccif_ctrl->hif_id,\n"
         "\t\tccci_ccif_ctrl, &ccci_hif_ccif_ops, &pdev->dev);\n#else\n"
         "\tccci_hif_register(ccif_ctrl->hif_id,\n\t\t(void *)ccci_ccif_ctrl, &ccci_hif_ccif_ops);\n#endif")
    edit("hif/ccci_dpmaif_com.c", "static int dpmaif_probe(struct platform_device *pdev)\n{",
         "static int dpmaif_probe(struct platform_device *pdev)\n{\n#if " + FLAG +
         "\n\tint error = ccci_tetris_hif_claim(pdev, DPMAIF_HIF_ID);\n"
         "\tif (error)\n\t\treturn error;\n#endif")
    edit("hif/ccci_dpmaif_com.c", "\tccci_hif_register(DPMAIF_HIF_ID, dpmaif_ctl, &g_dpmaif_ops);",
         "#if " + FLAG + "\n\tret = ccci_tetris_hif_register(DPMAIF_HIF_ID,\n"
         "\t\tdpmaif_ctl, &g_dpmaif_ops, dev);\n\tif (ret)\n\t\treturn ret;\n#else\n"
         "\tccci_hif_register(DPMAIF_HIF_ID, dpmaif_ctl, &g_dpmaif_ops);\n#endif")
    # No HIF resume/reset path is accepted by this one-shot boot profile.
    for name, function in (("hif/ccci_hif_ccif.c", "ccif_resume_noirq"),
                           ("hif/ccci_dpmaif_com.c", "dpmaif_resume_noirq"),
                           ("hif/ccci_dpmaif_com.c", "dpmaif_suspend_noirq")):
        anchor = f"static int {function}(struct device *dev)\n{{"
        edit(name, anchor, anchor + "\n#if " + FLAG + "\n\treturn -EOPNOTSUPP;\n#endif")
    registration = "fsm/register_prepare.h"
    edit(registration, "\t/* Successful probe means ONLY privately prepared resources. No publication.",
         "#if " + FLAG + "\n\tret = ccci_tetris_native_probe(md);\n\tif (ret)\n\t\tgoto abort_ports;\n#endif\n"
         "\t/* Successful probe means ONLY privately prepared resources. No publication.")
    # Private memory/physical ON admission replaces prepare-only denial ONLY
    # in the explicit native mode; no boolean provider is introduced.
    edit(registration, "\t/* Memory preparation alone does not own operational dependencies. */\n\treturn -EOPNOTSUPP;",
         "#if !" + FLAG + "\n\t/* Memory preparation alone does not own operational dependencies. */\n"
         "\treturn -EOPNOTSUPP;\n#endif")
    edit(registration, "\ttetris_commit_attempted = true;",
         "#if " + FLAG + "\n\tret = ccci_tetris_native_admit(md);\n\tif (ret)\n\t\tgoto out;\n#endif\n"
         "\ttetris_commit_attempted = true;")
    edit("fsm/modem_sys1.c", "\t(void)md;\n\treturn;\n#endif\n",
         "#if " + FLAG + "\n\t/* Preserve the already-owned layout; initialize native B4.1 bookkeeping. */\n"
         "\tmd->per_md_data.config.load_type = get_md_img_type();\n"
         "\tmd->per_md_data.config.setting |= MD_SETTING_ENABLE | MD_SETTING_FIRST_BOOT;\n"
         "\tmd->per_md_data.img_info[IMG_MD].type = IMG_MD;\n"
         "\tmd->per_md_data.img_info[IMG_MD].address = md->mem_layout.md_bank0.base_ap_view_phy;\n"
         "\tmd->per_md_data.img_info[IMG_DSP].type = IMG_DSP;\n"
         "\tmd->per_md_data.img_info[IMG_ARMV7].type = IMG_ARMV7;\n#endif\n"
         "\t(void)md;\n\treturn;\n#endif\n")
    # Only START's guard is relaxed. STOP, lifecycle and monitor stay denied.
    anchor = "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n\t/* No physical stop/start contract is provided by registration. */"
    source = after[E + "fsm/ccci_fsm.c"]
    start = source.index("static void fsm_routine_start(")
    at = source.index(anchor, start)
    require(at < source.index("static void fsm_routine_stop("), "START guard order drift")
    source = source[:at] + source[at:].replace(anchor,
        "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER) && !" + FLAG +
        "\n\t/* No physical stop/start contract is provided by registration. */", 1)
    source += "\n#if " + FLAG + "\nint ccci_tetris_native_queue_start(void)\n{\n"
    source += "\tint ret = ccci_tetris_owner_entry();\n\tif (ret)\n\t\treturn ret;\n"
    source += "\treturn fsm_append_command(ccci_fsm_entries, CCCI_COMMAND_START, 0);\n}\n#endif\n"
    after[E + "fsm/ccci_fsm.c"] = source
    return after


def apply_check(text, before, expected):
    with tempfile.TemporaryDirectory(prefix="tetris-native-start-apply-") as directory:
        root = Path(directory)
        for name, data in before.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        for check in (True, False):
            command = ["git", "apply", "--verbose", "--whitespace=error"]
            if check:
                command.append("--check")
            result = subprocess.run(command + ["-"], cwd=root, input=text, text=True,
                capture_output=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": str(root.parent)})
            require(result.returncode == 0 and not re.search(r"Skipped patch|\boffset\b|\bfuzz\b", result.stderr),
                    "native-start patch application failed: " + result.stderr)
        for name, data in expected.items():
            require((root / name).read_text() == data, "native-start output differs: " + name)


def pristine_inputs(linux):
    """Only three pristine d84 files are needed for native reconstruction."""
    linux = Path(linux).absolute()
    require(linux.resolve() == linux, "pristine kernel input traverses symlinks")
    real = load("native_start_pristine_pin", HERE.parent / "real-boot/stage.py")
    expected = dict(real.native.BASE_HASHES)
    evidence = json.loads((HERE.parent / "real-boot/SOURCE-EVIDENCE.json").read_text())
    require(evidence["pins"]["linux"] == LINUX, "pristine Linux revision differs")
    expected[real.KCONFIG] = evidence["sources"]["linux:" + real.KCONFIG]["sha256"]
    for name, digest in expected.items():
        path = linux / name
        require(path.resolve() == path and path.is_file() and
                hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                "missing/non-pristine d84 reconstruction input: " + name)
    return expected


def build(vendor=None, linux=None):
    vendor = vendor or UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878"
    linux = linux or UPSTREAM / ("linux-" + LINUX)
    pristine_inputs(linux)
    real = load("native_start_real_boot", HERE.parent / "real-boot/stage.py")
    closure = load("native_start_vendor_closure", REPO / "patches/modem/drafts/runtime-link-closure/link_full.py")
    with tempfile.TemporaryDirectory(prefix="tetris-native-start-source-") as directory:
        root = Path(directory)
        kernel = root / "kernel"
        with contextlib.redirect_stdout(io.StringIO()):
            baseline, _ = real.baseline(linux, kernel)
            native = real.candidate(baseline)
            manifest, _ = closure.stage(vendor, root / "vendor", {})
        paths = ("Kconfig", "Makefile", "fsm/modem_sys1.c", "fsm/ccci_fsm.c",
                 "fsm/register_prepare.h", "hif/ccci_hif.c", "hif/ccci_hif_ccif.c", "hif/ccci_dpmaif_com.c")
        before = {E + path: (root / "vendor" / E / path).read_text() for path in paths}
        require(manifest["vendor_commit"] == VENDOR, "not exact B4.1 CCCI")
    native_after = native_candidate(native)
    vendor_after = vendor_candidate(before)
    return {"native-on-api.patch": (patch(native, native_after), native, native_after),
            "ccci-native-start.patch.vendor": (patch(before, vendor_after), before, vendor_after)}


def verify_manifest():
    data = json.loads((HERE / "STAGING.json").read_text())
    actual = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
              for f in HERE.iterdir() if f.is_file() and f.name != "STAGING.json"}
    require(actual == data["files_sha256"], "native-start manifest closure differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path)
    parser.add_argument("--linux", type=Path)
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    bundles = build(args.vendor, args.linux)
    if args.emit:
        print(json.dumps({name: value[0] for name, value in bundles.items()}))
        return
    verify_manifest()
    for name, (data, before, after) in bundles.items():
        require((HERE / name).read_text() == data, "reviewed native-start overlay drift: " + name)
        apply_check(data, before, after)
    print("Exact native-ON + complete B4.1 operational CCCI overlay application: PASS; no compilation")


if __name__ == "__main__":
    main()
