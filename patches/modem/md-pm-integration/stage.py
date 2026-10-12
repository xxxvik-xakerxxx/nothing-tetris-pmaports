#!/usr/bin/env python3
"""Generate/check the observation-only patch against exact packaged MD sources."""

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
PREFIX = "drivers/pmdomain/mediatek/"
CFILE = PREFIX + "mtk-pm-domains.c"
DATA = PREFIX + "mt6878-modem-pm.h"
ADOPT = PREFIX + "mt6878-modem-adopt.h"
PATCH = HERE / "native-on-adoption.patch"
BASE_HASHES = {
    CFILE: "1bc964d9b4493fe23ac5955e4198fd2219f6e60ecad360cf2fa78518009a4841",
    PREFIX + "mtk-pm-domains.h": "6784f50366a74c5607d0f66ff397a6b72a148ea396ba0a6d6be92db9f0764e9e",
}
MD_PATCH = "0113-pmdomain-mediatek-mt6878-modem-power.patch"
MD_HASH = "03924af715632607de8329d18a7ccdff3f6d403ff4315863fe6b5d3418d90cac"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("packaged source context changed: " + old)
    return text.replace(old, new, 1)


def apply(root, text):
    # Use the same context matcher on macOS and Linux. The legacy packaged
    # hunks are hash-pinned; their existing whitespace must be preserved.
    result = subprocess.run(["git", "apply", "--verbose", "--whitespace=nowarn", "-"],
                            input=text, cwd=root, text=True, capture_output=True,
                            env={**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE)})
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    if "Skipped patch" in result.stderr:
        raise ValueError("source application skipped a file: " + result.stderr)
    for path in re.findall(r"^\+\+\+ b/(\S+)$", text, re.M):
        if "Checking patch " + path not in result.stderr:
            raise ValueError("source application did not check: " + path)


def packaged(kernel, output):
    spec = importlib.util.spec_from_file_location("md_power_sections", ROOT / "scripts/check-mt6878-modem-power.py")
    power = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(power)
    power.FILES = {CFILE, PREFIX + "mtk-pm-domains.h", DATA}
    for path, expected in BASE_HASHES.items():
        data = (kernel / path).read_bytes()
        if digest(data) != expected:
            raise ValueError("not pristine Linux d84 input: " + path)
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kernel / path, target)
    if digest((PACKAGE / MD_PATCH).read_bytes()) != MD_HASH:
        raise ValueError("packaged0113 changed; re-review before generation")
    names = list(dict.fromkeys(re.findall(r"^\s+([\w.-]+\.patch)$", (PACKAGE / "APKBUILD").read_text(), re.M)))
    if MD_PATCH not in names:
        raise ValueError("packaged0113 not selected by APKBUILD")
    inputs = []
    for name in names:
        raw = (PACKAGE / name).read_bytes()
        selected = "".join(power.sections(raw.decode("latin-1")))
        if selected:
            apply(output, selected)
            inputs.append({"patch": name, "sha256": digest(raw)})
    return {path: (output / path).read_text() for path in power.FILES}, inputs


def candidate(before):
    after = dict(before)
    c = before[CFILE]
    c = replace_once(c, "struct scpsys_domain {", "struct mt6878_md_adoption;\n\nstruct scpsys_domain {")
    c = replace_once(c, "\tint md_error;\n\tbool md_owned;", "\tstruct mt6878_md_adoption *md_adoption;")
    c = replace_once(c, "\t\tret = mt6878_md_check_off(pd);", "\t\tret = mt6878_md_adopt_init(pd, node);")
    c = replace_once(c, "\t\tpd->genpd.power_off = mt6878_md_power_off;\n\t\tpd->genpd.power_on = mt6878_md_power_on;",
                     "\t\tpd->genpd.power_off = mt6878_md_adopt_transition;\n"
                     "\t\tpd->genpd.power_on = mt6878_md_adopt_transition;\n"
                     "\t\tpd->genpd.attach_dev = mt6878_md_adopt_attach;\n"
                     "\t\tpd->genpd.detach_dev = mt6878_md_adopt_detach;")
    c = replace_once(c, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_KEEP_DEFAULT_OFF))\n\t\tpm_genpd_init(&pd->genpd, NULL, true);",
                     "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n"
                     "\t\tret = pm_genpd_init(&pd->genpd, NULL, false);\n"
                     "\t\tif (ret)\n\t\t\tgoto err_put_subsys_clocks;\n"
                     "\t} else if (MTK_SCPD_CAPS(pd, MTK_SCPD_KEEP_DEFAULT_OFF))\n"
                     "\t\tpm_genpd_init(&pd->genpd, NULL, true);")
    c = replace_once(c, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tif (!ret)\n\t\t\tmt6878_md_cleanup(pd);\n\t} else if (scpsys_domain_is_on(pd)) {",
                     "\t/* Removing an unpublished observation never shuts inherited MD down. */\n"
                     "\tif (!MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD) && scpsys_domain_is_on(pd)) {")
    after[CFILE] = c
    prefix = before[DATA].split("static int mt6878_md_check_off(", 1)
    if len(prefix) != 2:
        raise ValueError("missing exact native MD data/transition boundary")
    after[DATA] = replace_once(prefix[0], "MTK_SCPD_MT6878_MD | MTK_SCPD_KEEP_DEFAULT_OFF |",
                              "MTK_SCPD_MT6878_MD |") + '#include "mt6878-modem-adopt.h"\n'
    after[ADOPT] = (HERE / "mt6878-modem-adopt.h").read_text()
    return after


def diff(before, after):
    text = "From: Tetris port maintainers\nSubject: [STAGING PATCH] native MT6878 MD: observe inherited ON without transitions\n\n"
    text += "Not shipping. Requires guarded final-producer markers and the actual\ncompleted boot transaction. Consumer remains disabled. detach_dev is void:\nconsumer unbind cannot be vetoed; detach retires the observation only.\n\n"
    for path in sorted(after):
        if before.get(path) == after[path]:
            continue
        text += "diff --git a/" + path + " b/" + path + "\n"
        if path not in before:
            text += "new file mode 100644\n"
        text += "".join(difflib.unified_diff(before.get(path, "").splitlines(True),
                                          after[path].splitlines(True),
                                          fromfile="a/" + path if path in before else "/dev/null",
                                          tofile="b/" + path))
    return text


def validate(kernel, emit=False):
    # All disposable writes remain inside this bounded staging directory.
    with tempfile.TemporaryDirectory(prefix=".source-check-", dir=HERE) as temp:
        output = Path(temp)
        before, inputs = packaged(kernel, output)
        after = candidate(before)
        generated = diff(before, after)
        if emit:
            return generated, before, after, inputs
        if PATCH.read_text() != generated:
            raise ValueError("checked-in staging patch differs from canonical source/generation")
        result = subprocess.run(["git", "apply", "--check", "--verbose", str(PATCH)],
                                cwd=output, text=True, capture_output=True,
                                env={**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE)})
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        if "Skipped patch" in result.stderr or "Checking patch" not in result.stderr:
            raise ValueError("git apply did not check staging files: " + result.stderr)
        apply(output, generated)
        for path in after:
            if (output / path).read_text() != after[path]:
                raise ValueError("actual patch application differs: " + path)
        return generated, before, after, inputs


def contract(patch, before, after, inputs):
    return {
        "schema": 1,
        "phase": "staging-supplier-only-consumer-disabled",
        "pins": {
            "linux": "d84b264a54a37611f2f46bc19363cb9b41606205",
            "vendor": "ee2be53cb75670b548948636a0db1d1ff112bf12",
            "installed_uboot_source_basis": "8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5",
            "parent_personal_producer_source_reviewed_not_assumed_installed": "e2a916b716c593840291aad2e03de103bdb57e7d",
        },
        "patch": {"path": "native-on-adoption.patch", "sha256": digest(patch.encode())},
        "canonical_helper": {"path": "mt6878-modem-adopt.h", "target": ADOPT,
                             "sha256": digest(after[ADOPT].encode())},
        "packaged_inputs": inputs,
        "prepared_before_sha256": {path: digest(text.encode()) for path, text in sorted(before.items())},
        "staged_after_sha256": {path: digest(text.encode()) for path, text in sorted(after.items())},
        "producer_requirements": {
            "chosen_empty": "/chosen/tetris,modem-native-on-adoption-diagnostic",
            "supplier_empty_final_only": "nothing,modem-inherited-on-adoption",
            "supplier": "unique mediatek,mt6878-modem-power-controller; #power-domain-cells=1; sole available child reg0",
            "consumer": "unique mediatek,mddriver remains exactly disabled; no consumer activation",
            "metadata": "actual successful BROM80, descriptor32 and evidence336; retained nonoverlapping NOMAP allocations",
            "physical_observation": "PWR_ON+ACK30+ACK31=ON, EXTISO3=0, IFR9/IFR11/NEMI6:7 status=0",
        },
        "ci": {
            "source_check": "python3 -B patches/modem/md-pm-integration/stage.py --kernel <pristine-d84>",
            "static_tests": "python3 -B patches/modem/md-pm-integration/test_static.py",
            "apply": "CI=true GITHUB_ACTIONS=true python3 -B patches/modem/md-pm-integration/stage.py --kernel <pristine-d84> --prepared-kernel <prepared-kernel> --ci-apply",
            "config_fragment": "diagnostic.config",
            "required_resolved_config": {
                "ARM64": "y", "OF": "y", "PM": "y", "PM_GENERIC_DOMAINS": "y",
                "PM_GENERIC_DOMAINS_OF": "y", "MTK_SCPSYS_PM_DOMAINS": "y",
                "OF_DYNAMIC": "n", "MEMORY_HOTREMOVE": "n",
            },
            "targets": ["drivers/pmdomain/mediatek/mtk-pm-domains.o"],
            "actual_translation_unit": CFILE,
            "compile_status": "pending-no-local-native-compilation",
            "combined_link": "MD first; parent adapts camera native-provider.patch to this shared C; build shared object and one vmlinux; pending",
            "aggregate_readiness": "not-claimed-by-independent-object-checks",
        },
        "failed_requirements": {
            "consumer_unbind_veto": "detach_dev is void and cannot veto; detach retires observation with ESHUTDOWN, no teardown claim",
            "dynamic_supplier_removal": "existing suppress_bind_attrs only prevents userspace unbind; arbitrary in-kernel unregister unsupported",
            "present_packaged_config_runtime_adoption": "blocked by OF_DYNAMIC=y and MEMORY_HOTREMOVE=y; package unchanged",
        },
        "remaining": ["consumer activation/attachment", "first shutdown", "inhibited restart",
                      "suspend and secure-idle lifecycle", "current effective EMI permission lifetime", "SIM operation"],
        "hardware": "not-executed; no SMC/write/reset/activation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path,
                        default=ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")
    parser.add_argument("--emit-patch", action="store_true")
    parser.add_argument("--emit-contract", action="store_true")
    parser.add_argument("--prepared-kernel", type=Path,
                        help="check the exact pre-adoption files in a full packaged kernel tree")
    parser.add_argument("--ci-apply", action="store_true",
                        help="apply only in GitHub CI after exact prepared-file identity checks")
    args = parser.parse_args()
    if args.emit_patch and args.emit_contract:
        parser.error("choose one emission format")
    if args.ci_apply and (not args.prepared_kernel or args.emit_patch or
                         os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true"):
        parser.error("--ci-apply requires --prepared-kernel, CI=true and GITHUB_ACTIONS=true; never compile locally")
    patch, before, after, inputs = validate(args.kernel, emit=args.emit_patch)
    if args.prepared_kernel:
        for path in (CFILE, DATA):
            if (args.prepared_kernel / path).read_text() != before[path]:
                raise ValueError("prepared kernel differs from exact packaged baseline: " + path)
        if (args.prepared_kernel / ADOPT).exists():
            raise ValueError("prepared kernel already contains an adoption helper")
        if args.ci_apply:
            apply(args.prepared_kernel, patch)
            for path in after:
                if (args.prepared_kernel / path).read_text() != after[path]:
                    raise ValueError("CI patch result differs: " + path)
    if args.emit_patch:
        sys.stdout.write(patch)
    elif args.emit_contract:
        print(json.dumps(contract(patch, before, after, inputs), indent=2))
    else:
        print("PASS: exact packaged MD stack, deterministic adoption patch and exact Git context application")
        print("inputs=" + str(len(inputs)) + "; patch_sha256=" + digest(patch.encode()))


if __name__ == "__main__":
    main()
