"""Separate dormant supplier wiring and blocked ownership delta; no activation."""
import difflib
import hashlib
import json
import subprocess
import tarfile

PREFIX = "arch/arm64/boot/dts/mediatek/"
RESOURCES = "mt6878-camisp-supplier-resources-disabled.dtsi"
POWER = "mt6878-camisp-supplier-power-disabled.dtsi"
BOARD = "mt6878-nothing-tetris-camisp-supplier.dts"
MIGRATION = "mt6878-camisp-vmm-ownership-blocked.dtsi"
BLOCKED_BOARD = "mt6878-nothing-tetris-camisp-vmm-ownership-blocked.dts"
DESTINATIONS = {name: PREFIX + name for name in (RESOURCES, POWER, BOARD, MIGRATION, BLOCKED_BOARD)}
PARENT_INPUTS = (
    "patches/camera-camisp/native-integration/mt6878-native-vmm.inc",
    "patches/camera-camisp/native-integration/native-provider.patch",
    "patches/camera-camisp/power/mt6878-vmm-supplier.c",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0105-regulator-mt6315-read-active-voltage-selector.patch",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0109-regulator-mt6315-stop-mode-change-on-read-error.patch",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0110-regulator-mt6315-register-described-rails.patch",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0111-regulator-mt6315-fail-closed-shutdown.patch",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0113-regulator-mt6315-reject-unowned-phase-mask.patch",
    "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0114-regulator-mt6315-read-only-vgpu-observer.patch",
)
VENDOR_INPUTS = (
    "drivers/misc/mediatek/vmm_spm/mtk-vmm-spm.c",
    "drivers/misc/mediatek/mmdvfs/mtk-mmdvfs-debug.c",
    "drivers/soc/mediatek/mtk-mmdvfs-v3.c",
)
NATIVE_INPUTS = ("drivers/regulator/core.c", "drivers/regulator/of_regulator.c", "drivers/regulator/mt6315-regulator.c")


def trace(upstream, root, data):
    vendor = data["provenance"][0]
    native = next(row for row in data["provenance"] if row["repository"] == "MT6878-mainline/linux")
    rows = []
    for path in VENDOR_INPUTS:
        content = subprocess.check_output(["git", "-C", str(upstream / vendor["repository"]),
                                           "show", vendor["commit"] + ":" + path])
        rows.append({"repository": vendor["repository"], "commit": vendor["commit"],
                     "path": path, "sha256": hashlib.sha256(content).hexdigest()})
    prefix = "linux-" + native["commit"]
    with tarfile.open(upstream / (prefix + ".tar.gz")) as archive:
        for path in NATIVE_INPUTS:
            content = archive.extractfile(prefix + "/" + path).read()
            rows.append({"repository": native["repository"], "commit": native["commit"],
                         "path": path, "sha256": hashlib.sha256(content).hexdigest()})
    return {"provenance": rows, "parent_input_sha256": {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in PARENT_INPUTS}}


def plan(files):
    prefix = "patches/camera-camisp/resources/"
    return {
        "scope": "dormant supplier board plus explicitly blocked ownership delta; no CI/shipping changes",
        "sources": {prefix + name: destination for name, destination in DESTINATIONS.items()},
        "payload_sha256": {name: hashlib.sha256(files[name].encode()).hexdigest() for name in DESTINATIONS},
        "requires_existing_resource_header": prefix + "mediatek,mt6878-camisp-clock.h",
        "base": "mediatek/mt6878-nothing-tetris-native.dtb",
        "candidate": {
            "target": "mediatek/" + BOARD.replace(".dts", ".dtb"),
            "profile": "supplier", "runtime_activation": "disabled",
            "boot_eligibility": "baseline-preserving candidate only; CI and live boot untested",
            "native_vmm_config_variants": ["n", "y"],
        },
        "blocked_ownership": {
            "target": "mediatek/" + BLOCKED_BOARD.replace(".dts", ".dtb"),
            "profile": "ownership-blocked", "compile_only": True, "boot_allowed": False,
            "reason": "real supply opt-in with disabled rail/domains rejects active SPM probe",
        },
        "validator": prefix + "check-dt.py",
        "static_check": prefix + "check-supplier.py",
        "static_fixtures": prefix + "test-supplier.py",
        "parent_checks": ["compile exact baseline and both targets in CI only",
                          "validate each full DT delta and dt-schema",
                          "link canonical native VMM in CI; never use dummy MM_INFRA",
                          "do not install/boot ownership-blocked target"],
        "activation_blockers": ["regulator registration writes/unused cleanup/shutdown policy",
                                "VBUCK1 voltage/rate policy; bounds are not an operating point",
                                "vmmspm isolation notifier and MMDVFS Linux owner migration",
                                "MMUP/VCP firmware voltage/clock/isolation handoff",
                                "observed cold OFF rail, isolation, SRAM, ACKs and bus protection",
                                "live repeat, clean install, lifecycle and portability"],
    }


def outputs(data, fragment, power_fragment):
    resources = fragment(data, display_membership=False)
    resources = resources.replace(
        "Native CAM/ISP graph is supplied by the paired disabled diagnostic fixture.",
        "Dormant supplier graph only; display IOMMU membership stays unchanged.")
    power = power_fragment(data, supplier_only=True)
    power = power.replace(
        "Include ONLY in the isolated diagnostic board, after native-display and",
        "Dormant supplier description, after the unchanged native-display and")
    files = {
        RESOURCES: resources,
        POWER: power,
        BOARD: '''// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* Boot-preserving candidate, UNTESTED. No SPM supply opt-in or rail registration.
 * All new nodes are disabled; existing display/SCP/USB properties are inherited.
 */
#include "mt6878-nothing-tetris-native.dts"
#include "mt6878-camisp-supplier-resources-disabled.dtsi"
#include "mt6878-camisp-supplier-power-disabled.dtsi"
''',
        MIGRATION: '''// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* BLOCKED ownership description. Never include in a boot/install candidate.
 * Removing the observer selects regulator registration, not read-only access.
 * PMIC, VBUCK1 and CAM/ISP domains deliberately remain disabled. The active
 * native VMM guard rejects this pair before publishing SPM (including display).
 * Firmware handoff and voltage/rate policy must be resolved before revising it.
 */
&mt6319_gpu {
\t/delete-property/ mediatek,observe-vgpu-only;
};

&spm {
\tcam-vcore-supply = <&mt6319_6_vbuck1>;
\tisp-vcore-supply = <&mt6319_6_vbuck1>;
};
''',
        BLOCKED_BOARD: '''// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/* Compile-only ownership delta; NOT bootable with native VMM enabled. */
#include "mt6878-nothing-tetris-camisp-supplier.dts"
#include "mt6878-camisp-vmm-ownership-blocked.dtsi"
''',
    }
    for patch, names in (("supplier-description.patch", (RESOURCES, POWER, BOARD)),
                         ("ownership-description.patch", (MIGRATION, BLOCKED_BOARD))):
        code = ""
        for name in names:
            destination = DESTINATIONS[name]
            code += f"diff --git a/{destination} b/{destination}\nnew file mode 100644\n"
            code += "".join(difflib.unified_diff([], files[name].splitlines(True),
                                              fromfile="/dev/null", tofile="b/" + destination))
        files[patch] = code
    files["SUPPLIER-STAGING.json"] = json.dumps(plan(files), indent=2) + "\n"
    return files
