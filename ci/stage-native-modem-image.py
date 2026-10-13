#!/usr/bin/env python3
"""Stage a separate, frozen diagnostic package; never alter shipping inputs."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "cbb777d415b564c1e40598740288c0c9d953e745"
LINK_RUN = 38315490334
UBOOT_SOURCE = "322cf227f2ea26a7e319d20e3ce0321db8a38f15"
KERNEL = "device/testing/linux-postmarketos-mediatek-mt6878"
DEVICE = "device/testing/device-nothing-tetris"
BOARD = "mt6878-nothing-tetris-native-md-first-off"
INPUTS = {
    "patches/modem/md-pm-integration/native-on-adoption.patch":
        "715d68ba00491324752ddc8fe8c08e176422edf21645f3d78842bed41c82bc6a",
    "patches/camera-camisp/native-integration/native-provider-after-md.patch":
        "34845f753bdd21af7444f8e1bc5de8ca887a007a707463972a90c65211c9c99d",
}
DISABLED = (
    "OF_OVERLAY", "OF_UNITTEST", "OF_DYNAMIC", "MEMORY_HOTREMOVE",
    "PCI_DYNAMIC_OF_NODES", "I2C_DEMUX_PINCTRL", "CHROMEOS_OF_HW_PROBER",
    "VIDEO_QCOM_VENUS", "STM32_FIREWALL", "HOTPLUG_PCI_POWERNV",
    "MPC885ADS", "PPC_PSERIES", "CPU_IDLE", "ARM_PSCI_CPUIDLE",
    "ARM_PSCI_CPUIDLE_DOMAIN", "SUSPEND", "HIBERNATION", "HIBERNATE_CALLBACKS",
    "PM_SLEEP", "PM_SLEEP_SMP", "HOTPLUG_CPU", "MTK_DVFSRC", "ARM_PSCI_CHECKER",
    "KVM", "VIRTUALIZATION", "KEXEC", "KEXEC_FILE", "KEXEC_CORE", "KUNIT",
)
ENABLED = ("ARM64", "OF", "PM", "REGMAP", "REGULATOR", "PM_GENERIC_DOMAINS",
           "PM_GENERIC_DOMAINS_OF", "MTK_SCPSYS_PM_DOMAINS", "MTK_MT6878_NATIVE_VMM")
SUPPLIER_DTS = """
/ {
    chosen {
        tetris,modem-native-on-adoption-diagnostic;
        tetris,modem-first-off-diagnostic;
    };
};

&soc {
    nemicfg_ao_mem: syscon@10270000 {
        compatible = "mediatek,mt6878-nemicfg_ao_mem_reg_bus", "syscon";
        reg = <0x10270000 0x1000>;
        status = "disabled";
    };
};

&scpsys {
    md_spm: power-controller-modem {
        compatible = "mediatek,mt6878-modem-power-controller";
        #address-cells = <1>;
        #size-cells = <0>;
        #power-domain-cells = <1>;
        access-controllers = <&infracfg_ao>, <&nemicfg_ao_mem>;
        status = "disabled";

        power-domain@0 {
            reg = <0>;
            #power-domain-cells = <0>;
            status = "disabled";
        };
    };
};
"""


def frozen(path):
    source = Path(os.environ.get("TETRIS_NATIVE_SOURCE_TREE", str(ROOT)))
    return subprocess.check_output(["git", "-C", str(source), "show", SOURCE + ":" + path])


def change_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("absent or ambiguous package anchor: " + old)
    return text.replace(old, new, 1)


def configured(text):
    values = dict.fromkeys(DISABLED, "n") | dict.fromkeys(ENABLED, "y")
    lines = [line for line in text.splitlines()
             if not any(line.startswith("CONFIG_" + symbol + "=") or
                        line == "# CONFIG_" + symbol + " is not set" for symbol in values)]
    return "\n".join(lines + ["CONFIG_" + symbol + "=y" if value == "y" else
                              "# CONFIG_" + symbol + " is not set"
                              for symbol, value in sorted(values.items())]) + "\n"


def dt_patch():
    path = "arch/arm64/boot/dts/mediatek/" + BOARD + ".dts"
    hif = frozen("patches/modem/drafts/runtime-hif-dt/mt6878-nothing-tetris-ccci-hif-resources.dts").decode()
    board = hif + SUPPLIER_DTS
    return ("From: Tetris port maintainers\nSubject: [DIAGNOSTIC PATCH] separate native MD first-OFF board\n\n"
            "Not shipping. The signed final U-Boot producer alone enables MD supplier/domain0.\n"
            "The modem consumer and camera/GPU hardware remain disabled.\n\n"
            "diff --git a/Documentation/devicetree/bindings/power/mediatek,power-controller.yaml b/Documentation/devicetree/bindings/power/mediatek,power-controller.yaml\n"
            "--- a/Documentation/devicetree/bindings/power/mediatek,power-controller.yaml\n"
            "+++ b/Documentation/devicetree/bindings/power/mediatek,power-controller.yaml\n"
            "@@ -22,3 +22,3 @@\n   $nodename:\n"
            "-    pattern: '^power-controller(@[0-9a-f]+)?$'\n"
            "+    pattern: '^power-controller(-modem)?(@[0-9a-f]+)?$'\n \n"
            "diff --git a/" + path + " b/" + path + "\nnew file mode 100644\n" +
            "".join(difflib.unified_diff([], board.splitlines(True), fromfile="/dev/null", tofile="b/" + path)) +
            "diff --git a/arch/arm64/boot/dts/mediatek/Makefile b/arch/arm64/boot/dts/mediatek/Makefile\n"
            "--- a/arch/arm64/boot/dts/mediatek/Makefile\n+++ b/arch/arm64/boot/dts/mediatek/Makefile\n"
            "@@ -1,1 +1,2 @@\n+dtb-$(CONFIG_ARCH_MEDIATEK) += " + BOARD + ".dtb\n"
            " # SPDX-License-Identifier: GPL-2.0\n")


def stage(tree, report):
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("diagnostic image staging is GitHub CI-only")
    tree = tree.resolve()
    if tree == ROOT / "pmaports" or tree == ROOT:
        raise ValueError("refusing to mutate shipping checkout")
    package, device = tree / KERNEL, tree / DEVICE
    apk = (package / "APKBUILD").read_text()
    if "0180-native-md-first-off.patch" in apk:
        raise ValueError("diagnostic profile already staged")
    extra = {}
    for name, (path, expected) in zip(("0180-native-md-first-off.patch", "0181-native-camera-after-md.patch"), INPUTS.items()):
        data = frozen(path)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("frozen native source identity mismatch: " + path)
        extra[name] = data
    extra["0182-native-md-first-off-board.patch"] = dt_patch().encode()
    # The native leaf Makefile has a parent-header search path, but the parent
    # provider TU does not inherit it while including this nested header.
    extra["0183-native-camera-header-parent.patch"] = (
        "From: Tetris port maintainers\nSubject: [DIAGNOSTIC PATCH] native VMM: resolve the real parent header\n\n"
        "Same actual shared-provider header as the isolated link, with no research include flags.\n\n"
        "diff --git a/drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.h b/drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.h\n"
        "--- a/drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.h\n"
        "+++ b/drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.h\n"
        "@@ -8 +8 @@\n-#include \"mtk-pm-domains.h\"\n+#include \"../mtk-pm-domains.h\"\n"
    ).encode()
    anchor = '\t1200-vendor-sensor-framework-linux-6.18.patch.vendor\n'
    apk = change_once(apk, anchor, anchor + "".join("\t" + name + "\n" for name in extra))
    apk = change_once(apk, "pkgrel=182\n", "pkgrel=183\n")
    apk = change_once(apk, '\t\tImage.gz modules \\\n',
                      '\t\tImage.gz modules \\\n\t\tmediatek/' + BOARD + '.dtb \\\n')
    install_native = ('\tinstall -Dm644 "$builddir/arch/$_carch/boot/dts/mediatek/mt6878-nothing-tetris-native.dtb" \\\n'
                      '\t\t"$pkgdir/boot/dtbs/mediatek/mt6878-nothing-tetris-native.dtb"\n')
    apk = change_once(apk, install_native, install_native +
                     '\tinstall -Dm644 "$builddir/arch/$_carch/boot/dts/mediatek/' + BOARD + '.dtb" \\\n' +
                     '\t\t"$pkgdir/boot/dtbs/mediatek/' + BOARD + '.dtb"\n')
    checks = ("\t# This diagnostic profile must exclude every competing idle/sleep writer.\n"
              "\tfor _symbol in " + " ".join(DISABLED) + "; do\n"
              '\t\tif grep -Eq "^CONFIG_${_symbol}=[ym]$" .config; then\n'
              '\t\t\tdie "native MD diagnostic exclusion unresolved: $_symbol"\n\t\tfi\n\tdone\n'
              "\tfor _symbol in " + " ".join(ENABLED) + "; do\n"
              '\t\tgrep -Fxq "CONFIG_${_symbol}=y" .config || die "native MD dependency unresolved: $_symbol"\n\tdone\n')
    apk = change_once(apk, '\tmake ARCH="$_carch" LLVM=1 olddefconfig\n',
                      '\tmake ARCH="$_carch" LLVM=1 olddefconfig\n' + checks)
    # checksum is recomputed by pmbootstrap, not bypassed.
    for name, data in extra.items():
        (package / name).write_bytes(data)
    config = package / "config-postmarketos-mediatek-mt6878.aarch64"
    config.write_text(configured(config.read_text()))
    (package / "APKBUILD").write_text(apk)
    info = device / "deviceinfo"
    info.write_text(change_once(info.read_text(), 'deviceinfo_dtb="mt6878-nothing-tetris-native"',
                               'deviceinfo_dtb="' + BOARD + '"'))
    device_apk = device / "APKBUILD"
    device_apk.write_text(change_once(device_apk.read_text(), "pkgrel=18\n", "pkgrel=19\n"))
    metadata = dict(profile="native-md-first-off-diagnostic", source_commit=SOURCE,
                    linked_kernel_run=LINK_RUN, required_uboot_commit=UBOOT_SOURCE,
                    kernel_package="7.2.1-r183", device_package="8-r19", board=BOARD,
                    changes={name: hashlib.sha256(data).hexdigest() for name, data in extra.items()},
                    native_include_correction="nested header resolves ../mtk-pm-domains.h; no provider behavior change",
                    sleep_idle_hotplug_allowed=False, modem_consumer_enabled=False,
                    camera_gpu_enabled=False, end_user_radio_functionality=False)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmaports", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.pmaports, args.report), indent=2))
