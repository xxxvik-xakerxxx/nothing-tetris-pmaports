#!/usr/bin/env python3
"""Compose a separate matched native-START package COPY; never activate hardware."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
KERNEL = "device/testing/linux-postmarketos-mediatek-mt6878"
DEVICE = "device/testing/device-nothing-tetris"
CONFIG = "config-postmarketos-mediatek-mt6878.aarch64"
BOARD = "mt6878-nothing-tetris-native-md-start-candidate"
UTIL = "drivers/misc/mediatek/ccci_util/"
PLATFORM = "drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c"
NATIVE = "MTK_MT6878_MODEM_NATIVE_START_STAGING"
OVERLAYS = ("0200-native-owner.patch.vendor", "0201-native-ports.patch.vendor",
            "0202-native-prepare.patch.vendor", "0203-native-lifecycle.patch.vendor",
            "0204-native-smem-common.patch.vendor", "0205-native-smem-consumer.patch.vendor",
            "0206-native-ccci-start.patch.vendor", "0207-native-util-metadata.patch.vendor",
            "0208-native-smem-provider.patch.vendor", "0209-native-image-runtime.patch.vendor")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(data, algorithm="sha256"):
    return hashlib.new(algorithm, data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    abi = load("native_image_abi", HERE.parent / "abi.py")
    previous = sys.modules.get("abi")
    sys.modules["abi"] = abi
    try:
        link = load("native_image_link", HERE.parent / "link.py")
    finally:
        if previous is None:
            del sys.modules["abi"]
        else:
            sys.modules["abi"] = previous
    return link, abi


def once(text, old, new):
    require(text.count(old) == 1, "missing/ambiguous source anchor: " + old[:100])
    return text.replace(old, new, 1)


def patch(before, after):
    output = ""
    for name in sorted(after):
        if before.get(name) == after[name]:
            continue
        output += "diff --git a/" + name + " b/" + name + "\n"
        if name not in before:
            output += "new file mode 100644\n"
        output += "".join(difflib.unified_diff(before.get(name, "").splitlines(True), after[name].splitlines(True),
            fromfile="a/" + name if name in before else "/dev/null", tofile="b/" + name))
    return output.encode()


def runtime(before):
    after = dict(before)
    assets = {"util-log.h": "tetris_image_log.h", "util-events.h": "tetris_image_events.h",
              "util-pin.h": "tetris_image_pin.h", "util-api.h": "tetris_image_util_api.h"}
    for local, target in assets.items():
        after[UTIL + target] = (HERE / local).read_text()
    for source, header in (("ccci_private_log.c", "tetris_image_log.h"),
                           ("ccci_util_broadcast.c", "tetris_image_events.h"),
                           ("ccci_util_pin_broadcast.c", "tetris_image_pin.h")):
        after[UTIL + source] += '\n#include "' + header + '"\n'
    for source in ("ccci_private_log.c", "ccci_util_broadcast.c", "ccci_util_pin_broadcast.c",
                   "ccci_util_lib_main.c", "ccci_util_lib_sys.c"):
        after[UTIL + source] = once(after[UTIL + source], '#include "ccci_util_log.h"\n' if
            source != "ccci_util_lib_main.c" else '#include "ccci_util_lib_main.h"\n',
            ('#include "ccci_util_log.h"\n' if source != "ccci_util_lib_main.c" else
             '#include "ccci_util_lib_main.h"\n') + '#include "tetris_image_util_api.h"\n')
    main = after[UTIL + "ccci_util_lib_main.c"]
    main = once(main, "\tint ret = mtk_ccci_args_key_val_init();\n", "\tint ret;\n\n"
        "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
        "\tret = ccci_tetris_log_init();\n\tif (ret)\n\t\treturn ret;\n"
        "\tret = ccci_tetris_events_init();\n\tif (ret)\n\t\tgoto native_log_fail;\n"
        "\tret = ccci_tetris_pin_init();\n\tif (ret)\n\t\tgoto native_events_fail;\n"
        "\tret = ccci_common_sysfs_init();\n\tif (ret)\n\t\tgoto native_pin_fail;\n"
        "\t/* No new fallible AP initialization after owned_smem_init pins\n"
        "\t * its genuine mapping owner for the entire boot. */\n#endif\n"
        "\tret = mtk_ccci_args_key_val_init();\n")
    cleanup = "\tmtk_ccci_owned_args_cleanup();\n\treturn ret;\n"
    main = once(main, cleanup, "\tmtk_ccci_owned_args_cleanup();\n"
        "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
        "\tccci_tetris_sysfs_exit();\nnative_pin_fail:\n\tccci_tetris_pin_exit();\n"
        "native_events_fail:\n\tccci_tetris_events_exit();\nnative_log_fail:\n"
        "\tccci_tetris_log_exit();\n#endif\n\treturn ret;\n")
    main = once(main, "static void __exit ccci_util_metadata_exit(void)\n{\n",
        "static void __exit ccci_util_metadata_exit(void)\n{\n"
        "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
        "\tccci_tetris_sysfs_exit();\n\tccci_tetris_pin_exit();\n"
        "\tccci_tetris_events_exit();\n\tccci_tetris_log_exit();\n#endif\n")
    after[UTIL + "ccci_util_lib_main.c"] = main
    system = after[UTIL + "ccci_util_lib_sys.c"]
    system = once(system, "static struct attribute *ccci_default_attrs[] = {\n",
        "static struct attribute *ccci_default_attrs[] = {\n"
        "#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
        "\t/* No boot/reset/PIN control surface in the retained native profile. */\n"
        "\t&ccci_attr_version.attr,\n\t&ccci_attr_md_chn.attr,\n#else\n")
    system = once(system, "\t&ccci_attr_pincfg.attr,\n\tNULL\n", "\t&ccci_attr_pincfg.attr,\n#endif\n\tNULL\n")
    system += ("\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
               "void ccci_tetris_sysfs_exit(void)\n{\n"
               "\tif (ccci_sys_info)\n\t\tkobject_put(&ccci_sys_info->kobj);\n}\n#endif\n")
    after[UTIL + "ccci_util_lib_sys.c"] = system
    source = after[PLATFORM]
    source = once(source, "static int md_cd_get_modem_hw_info(", '#include "native-image-consumer-resources.h"\n\nstatic int md_cd_get_modem_hw_info(')
    start = source.index('\tret = of_property_read_u32(dev_ptr->dev.of_node,\n\t\t"mediatek,offset-epon-md1"')
    end = source.index("\n\t/* Device tree using none flag", start)
    legacy = source[start:end]
    require("ioremap_wc(0x1C803000, 0x1000)" in legacy and "irq_of_parse_and_map" in legacy,
            "NOS resource fallback/IRQ source changed")
    source = source[:start] + ("#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)\n"
        "\tret = ccci_tetris_consumer_resources(dev_ptr, hw_info);\n"
        "\tif (ret)\n\t\treturn ret;\n#else\n" + legacy + "\n#endif\n") + source[end:]
    after[PLATFORM] = source
    after[str(Path(PLATFORM).parent / "native-image-consumer-resources.h")] = (HERE / "consumer-resources.h").read_text()
    return patch(before, after), after


def sources(vendor, pristine):
    link, abi = helpers()
    link.verify_manifest()
    inputs = link.source_inputs(vendor, pristine)
    start, real, _, bundles, metadata, _, providers = inputs
    owner = load("image_owner", ROOT / "patches/modem/check_transport_owner.py")
    stack = [owner.bundle().encode(), (ROOT / "patches/modem/drafts/runtime-ports/runtime-ports.patch.vendor").read_bytes(),
        (ROOT / "patches/modem/drafts/runtime-prepare/runtime-prepare.patch.vendor").read_bytes(),
        (ROOT / "patches/modem/drafts/runtime-lifecycle/runtime-lifecycle.patch.vendor").read_bytes(),
        providers["common.overlay"][0].encode(), providers["consumer.overlay"][0].encode(),
        bundles["ccci-native-start.patch.vendor"][0].encode(), metadata.encode(), providers["provider.overlay"][0].encode()]
    with tempfile.TemporaryDirectory(prefix="tetris-image-sources-") as directory:
        target = Path(directory).resolve() / "vendor"
        link.stage_vendor(vendor, target, inputs)
        before = {UTIL + name: (target / UTIL / name).read_text() for name in (
            "ccci_private_log.c", "ccci_util_broadcast.c", "ccci_util_pin_broadcast.c", "ccci_util_lib_main.c", "ccci_util_lib_sys.c")}
        before[PLATFORM] = (target / PLATFORM).read_text()
        data, after = runtime(before)
        link.apply_checked(real, target, data.decode(), before, after)
    stack.append(data)
    kernel = dict(real.recipes()[1])
    kernel["0189-native-modem-start-api.patch"] = bundles["native-on-api.patch"][0].encode()
    dt_source = ('// SPDX-License-Identifier: GPL-2.0-only\n#include "' + real.stage.parent.BOARD + '.dts"\n\n'
        '&mddriver {\n\tstatus = "disabled";\n\tpower-domains = <&md_spm 0>;\n'
        '\tmediatek,mdhif-type = <6>;\n\tmediatek,cldma-capability = <14>;\n'
        '\tmediatek,offset-epon-md1 = <0x64 6>;\n\tmediatek,boot-status-config = <1>;\n'
        '\treg = <0 0x0d180000 0 0x2000>, <0 0x1c803000 0 0x1000>;\n'
        '\tinterrupts = <GIC_SPI 491 IRQ_TYPE_LEVEL_HIGH 0>,\n'
        '\t\t<GIC_SPI 228 IRQ_TYPE_LEVEL_HIGH 0>, <GIC_SPI 229 IRQ_TYPE_LEVEL_HIGH 0>;\n'
        '\tccci-infracfg = <&infracfg_ao>;\n};\n\n&soc {\n'
        '\tccif@10209000 { status = "disabled"; };\n'
        '\tdpmaif@10014000 { status = "disabled"; };\n'
        '\tccif@1024d000 { status = "disabled"; };\n'
        '\tccif@1025d000 { status = "disabled"; };\n};\n')
    dt_path = "arch/arm64/boot/dts/mediatek/" + BOARD + ".dts"
    kernel["0190-native-modem-start-board.patch"] = patch({}, {dt_path: dt_source}) + (
        "diff --git a/arch/arm64/boot/dts/mediatek/Makefile b/arch/arm64/boot/dts/mediatek/Makefile\n"
        "--- a/arch/arm64/boot/dts/mediatek/Makefile\n+++ b/arch/arm64/boot/dts/mediatek/Makefile\n"
        "@@ -1,1 +1,2 @@\n+dtb-$(CONFIG_ARCH_MEDIATEK) += " + BOARD + ".dtb\n # SPDX-License-Identifier: GPL-2.0\n").encode()
    return link, abi, real, kernel, dict(zip(OVERLAYS, stack)), after


def configured(text, real):
    values = dict.fromkeys(real.DISABLED, "n") | dict.fromkeys((*real.REQUIRED, *real.REAL, NATIVE), "y")
    lines = [line for line in text.splitlines() if not any(line.startswith("CONFIG_" + name + "=") or
        line == "# CONFIG_" + name + " is not set" for name in values)]
    return "\n".join(lines + ["CONFIG_" + name + "=y" if value == "y" else
        "# CONFIG_" + name + " is not set" for name, value in sorted(values.items())]) + "\n"


def checksums(apk, files):
    match = re.search(r'^sha512sums="\n(.*?)^"', apk, re.M | re.S)
    require(match, "missing package checksum block")
    rows = dict((name, value) for value, name in re.findall(r"^([0-9a-f]{128})  (\S+)$", match[1], re.M))
    require(len(rows) == len(re.findall(r"^([0-9a-f]{128})  (\S+)$", match[1], re.M)), "duplicate checksum identity")
    rows.update({name: sha(data, "sha512") for name, data in files.items()})
    return apk[:match.start(1)] + "".join(value + "  " + name + "\n" for name, value in rows.items()) + apk[match.end(1):]


def extend(apk, config, kernel, overlays, real, revision):
    additions = {**kernel, **overlays}
    additions.update({"native-image-prepare.py": (HERE / "prepare.py").read_bytes(),
        "native-image-check.py": (HERE / "check_modules.py").read_bytes(),
        "native-image-dt-check.py": (HERE / "check_dt.py").read_bytes(),
        "native_image_dt.py": (ROOT / "patches/modem/check_preflight_dt.py").read_bytes(),
        "native_image_abi.py": (HERE.parent / "abi.py").read_bytes(),
        "native-image.Kbuild": (HERE.parent / "Kbuild").read_bytes(),
        "native-image-shipping.config": (ROOT / "pmaports" / KERNEL / CONFIG).read_bytes()})
    script = (HERE / "native-image.sh").read_text()
    args = "\n".join('\t\t"$srcdir/' + name + '"' + (' \\' if i + 1 < len(overlays) else '')
                     for i, name in enumerate(overlays))
    additions["native-image.sh"] = once(script, "@PATCHES@", args).encode()
    additions["native-image-modprobe.conf"] = ("# Unqualified native modem candidate: no automatic module load.\n" +
        "".join("blacklist " + name + "\ninstall " + name + " /bin/false\n" for name in (
            "ccci_util_lib", "ccci_md_all", "ccci_auxadc", "ccci_ccif", "ccci_dpmaif", "ccci_cldma",
            "ccci_fsm_scp", "ccmni", "rps_perf"))).encode()
    apk = once(apk, "pkgrel=188\n", "pkgrel=" + str(revision) + "\n")
    apk = once(apk, "\t0187-native-modem-wakeup-sleep-veto.patch\n",
        "\t0187-native-modem-wakeup-sleep-veto.patch\n" + "".join("\t" + name + "\n" for name in additions))
    apk = once(apk, "prepare() {\n", 'prepare() {\n\t. "$srcdir/native-image.sh"\n')
    apk = once(apk, "build() {\n", 'build() {\n\t. "$srcdir/native-image.sh"\n')
    apk = once(apk, '\t\t< "$srcdir"/0051-vendor-camera-tetris-compile-only-audit.patch.vendor\n',
        '\t\t< "$srcdir"/0051-vendor-camera-tetris-compile-only-audit.patch.vendor\n\t_prepare_native_start\n')
    disabled = " ".join(real.DISABLED)
    required = " ".join((*real.REQUIRED, *real.REAL, NATIVE))
    gate = ('\tfor _symbol in ' + disabled + '; do\n'
        '\t\tif grep -Eq "^CONFIG_${_symbol}=[ym]$" .config; then die "unsafe native selector: $_symbol"; fi\n\tdone\n'
        '\tfor _symbol in ' + required + '; do\n'
        '\t\tgrep -Fxq "CONFIG_${_symbol}=y" .config || die "native dependency missing: $_symbol"\n\tdone\n')
    apk = once(apk, '\tmake ARCH="$_carch" LLVM=1 olddefconfig\n', '\tmake ARCH="$_carch" LLVM=1 olddefconfig\n' + gate)
    apk = once(apk, "\t_build_modem_link\n\t_build_ccci_metadata_only\n", "\t_build_native_start\n")
    apk = once(apk, '\tdepmod -b "$pkgdir" "$_release"\n', '\t. "$srcdir/native-image.sh"\n\t_package_native_start\n\tdepmod -b "$pkgdir" "$_release"\n')
    apk = once(apk, "\t\tImage.gz modules \\\n", "\t\tImage.gz modules \\\n\t\tmediatek/" + BOARD + ".dtb \\\n")
    anchor = '\trm -f "$pkgdir"/lib/modules/*/build "$pkgdir"/lib/modules/*/source\n'
    apk = once(apk, anchor, '\tinstall -Dm644 "$builddir/arch/$_carch/boot/dts/mediatek/' + BOARD + '.dtb" \\\n'
        '\t\t"$pkgdir/boot/dtbs/mediatek/' + BOARD + '.dtb"\n' + anchor)
    apk = once(apk, 'makedepends="\n', 'makedepends="\n\tpy3-elftools\n\tdtc\n')
    config = configured(config, real)
    return apk, config, additions


def regular(path):
    require(path.resolve() == path and path.is_file() and path.stat().st_nlink == 1,
            "independent regular package COPY input required: " + str(path))
    return path.read_bytes()


def plan(tree, vendor, pristine, revision):
    require(type(revision) is int and 189 < revision <= 2147483647, "explicit distinct pkgrel >189 required")
    link, abi, real, kernel, overlays, _ = sources(vendor, pristine)
    bridge = load("image_gnss_bridge", ROOT / "ci/stage-native-gnss-candidate-image.py")
    apk = regular(tree / KERNEL / "APKBUILD").decode()
    names = re.findall(r"^([0-9a-f]{128})  (\S+)$", apk, re.M)
    inputs = {KERNEL + "/" + name: regular(tree / KERNEL / name) for _, name in names
              if (ROOT / "pmaports" / KERNEL / name).is_file()}
    for value, name in names:
        if KERNEL + "/" + name in inputs:
            require(sha(inputs[KERNEL + "/" + name], "sha512") == value, "package source checksum differs: " + name)
    base = (KERNEL + "/APKBUILD", KERNEL + "/" + CONFIG, DEVICE + "/APKBUILD", DEVICE + "/deviceinfo", DEVICE + "/boot_image.its")
    inputs.update({name: regular(tree / name) for name in base})
    for name, data in inputs.items():
        require(data == regular(ROOT / "pmaports" / name), "fresh package differs from reviewed source: " + name)
    require(not (tree / ".tetris-image-evidence").exists(), "candidate COPY is already composed")
    with tempfile.TemporaryDirectory(prefix="tetris-native-image-") as directory:
        scratch = Path(directory).resolve() / "copy"
        for relative, data in inputs.items():
            path = scratch / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        parent = bridge.stage(scratch, scratch / "native.json", scratch / "tx.json", include_tx=True)
        require(parent["required_uboot_commit"] == "f25c01444a642c6fca857bd9678ef438ec371988", "SCP/f25 loader changed")
        package = scratch / KERNEL
        new_apk, cfg, additions = extend((package / "APKBUILD").read_text(), (package / CONFIG).read_text(),
                                       kernel, overlays, real, revision)
        abi.security_profile(abi.config((ROOT / "pmaports" / KERNEL / CONFIG).read_text()), abi.config(cfg))
        for name, data in additions.items():
            require(not (package / name).exists(), "candidate output collision: " + name)
            (package / name).write_bytes(data)
        (package / CONFIG).write_text(cfg)
        local = {path.name: path.read_bytes() for path in package.iterdir() if path.is_file()}
        generated = {name: data for name, data in local.items() if name not in {Path(key).name for key in inputs}}
        new_apk = checksums(new_apk, {**generated, CONFIG: cfg.encode()})
        (package / "APKBUILD").write_text(new_apk)
        info = scratch / DEVICE / "deviceinfo"
        info.write_text(once(info.read_text(), 'deviceinfo_dtb="mt6878-nothing-tetris-native-md-first-off"', 'deviceinfo_dtb="' + BOARD + '"'))
        fit = scratch / DEVICE / "boot_image.its"
        fit.write_text(once(fit.read_text(), 'data = /incbin/("mt6878-nothing-tetris-native-md-first-off.dtb");', 'data = /incbin/("' + BOARD + '.dtb");'))
        device = scratch / DEVICE / "APKBUILD"
        device.write_text(checksums(device.read_text(), {"deviceinfo": info.read_bytes(), "boot_image.its": fit.read_bytes()}))
        outputs = {str(path.relative_to(scratch)): path.read_bytes() for path in scratch.rglob("*") if path.is_file()
                   and path.name not in ("native.json", "tx.json") and path.read_bytes() != inputs.get(str(path.relative_to(scratch)))}
    report = {"profile": "native-start-matched-disabled-candidate", "kernel_package": f"7.2.1-r{revision}",
        "board": BOARD, "fit_dtb": BOARD + ".dtb", "required_uboot_commit": parent["required_uboot_commit"],
        "parent": parent, "pins": {"linux": link.LINUX, "vendor": link.VENDOR, "companion_modules": link.MODULES_PIN},
        "changes_sha256": {name: sha(data) for name, data in outputs.items()},
        "validation": "source/package composition only; actual matching image build and hardware pending",
        "activation": "modem/CCIF/DPMAIF/CCIF4/CCIF5 and rails disabled; modprobe blacklist+install denial; no automatic START",
        "runtime_delta": "checked genuine log/broadcast/pin allocation + sysfs parent; actual consumer getter claims/maps/IRQ, no address fallback",
        "remaining": [text for text in link.BLOCKERS if not text.startswith(("Artifacts are not installed", "AP-only util exports"))] +
            ["New checked util/resource plumbing still needs actual candidate compilation/load validation; legacy SIB and user broadcast/reset devices remain uninstalled."],
        "stock_slot": "untouched; no bootloader selection/flash operation",
        "source_helpers_sha256": {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in (
            HERE.parent / "link.py", HERE.parent.parent / "native-start/stage.py", HERE.parent.parent / "real-boot/stage.py")}}
    return inputs, outputs, report


def stage(tree, vendor, pristine, report, revision, opt_in=False):
    link, _ = helpers()
    _, real, _ = link.helpers()
    real.require_ci()
    require(opt_in is True, "explicit --include-native-start-image required")
    verify_manifest()
    tree, report = link.input_path(tree), link.input_path(report)
    require(ROOT not in tree.parents and tree not in ROOT.parents and tree != ROOT and tree.is_dir(), "external independent pmaports COPY required")
    require(report != tree and tree in report.parents and
            not any(tree / name in report.parents for name in (KERNEL, DEVICE, ".tetris-image-evidence")), "report must be separate inside COPY")
    require(not report.exists(), "image report exists")
    inputs, outputs, result = plan(tree, vendor, pristine, revision)
    for name, data in inputs.items():
        require(regular(tree / name) == data, "package input changed during planning: " + name)
    for name in outputs:
        path = link.input_path(tree / name)
        require(tree in path.parents and (name in inputs or not path.exists()), "candidate output collision: " + name)
    for name, data in outputs.items():
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify_manifest():
    document = json.loads((HERE / "STAGING.json").read_text())
    require(document["files_sha256"] == {path.name: sha(path.read_bytes()) for path in HERE.iterdir()
            if path.is_file() and path.name != "STAGING.json"}, "image manifest closure differs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-check", action="store_true")
    parser.add_argument("--pmaports", type=Path)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--pristine-kernel", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--candidate-pkgrel", type=int)
    parser.add_argument("--include-native-start-image", action="store_true")
    args = parser.parse_args()
    if args.source_check:
        verify_manifest()
        _, _, _, kernel, overlays, _ = sources(args.vendor, args.pristine_kernel)
        result = {"validation": "actual source/strict patch application only; no compiler or target execution",
                  "kernel_sha256": {name: sha(data) for name, data in kernel.items()},
                  "vendor_sha256": {name: sha(data) for name, data in overlays.items()}}
    else:
        require(all((args.pmaports, args.report, args.candidate_pkgrel)), "stage requires COPY, report and explicit revision")
        result = stage(args.pmaports, args.vendor, args.pristine_kernel, args.report,
                       args.candidate_pkgrel, args.include_native_start_image)
    print(json.dumps(result, indent=2))
