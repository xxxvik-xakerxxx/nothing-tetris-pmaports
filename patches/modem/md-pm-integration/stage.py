#!/usr/bin/env python3
"""Generate/check native adoption, first-OFF and bounded restart staging."""

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
RESTART = PREFIX + "mt6878-modem-restart.h"
RESTART_TEST = PREFIX + "mt6878-modem-restart-test.h"
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
                     "\t\tret = pm_genpd_init(&pd->genpd, NULL,\n"
                     "\t\t\tpd->md_adoption->state == MT6878_MD_FIRST_OFF_COMPLETE);\n"
                     "\t\tif (ret) {\n"
                     "\t\t\tmt6878_md_first_off_publication_fault(scpsys, ret);\n"
                     "\t\t\tgoto err_put_subsys_clocks;\n\t\t}\n"
                     "\t} else if (MTK_SCPD_CAPS(pd, MTK_SCPD_KEEP_DEFAULT_OFF))\n"
                     "\t\tpm_genpd_init(&pd->genpd, NULL, true);")
    c = replace_once(c, "\tif (MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD)) {\n\t\tif (!ret)\n\t\t\tmt6878_md_cleanup(pd);\n\t} else if (scpsys_domain_is_on(pd)) {",
                     "\t/* Removing an unpublished observation never shuts inherited MD down. */\n"
                     "\tif (!MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD) && scpsys_domain_is_on(pd)) {")
    c = replace_once(c, "err_cleanup_domains:\n\tscpsys_domain_cleanup(scpsys);",
                     "err_cleanup_domains:\n\tmt6878_md_first_off_publication_fault(scpsys, ret);\n"
                     "\tscpsys_domain_cleanup(scpsys);")
    after[CFILE] = c
    prefix = before[DATA].split("static int mt6878_md_check_off(", 1)
    if len(prefix) != 2:
        raise ValueError("missing exact native MD data/transition boundary")
    after[DATA] = replace_once(prefix[0], "MTK_SCPD_MT6878_MD | MTK_SCPD_KEEP_DEFAULT_OFF |",
                              "MTK_SCPD_MT6878_MD |") + '#include "mt6878-modem-adopt.h"\n'
    after[ADOPT] = (HERE / "mt6878-modem-adopt.h").read_text()
    after[RESTART] = (HERE / "mt6878-modem-restart.h").read_text()
    after[RESTART_TEST] = (HERE / "mt6878-modem-restart-test.h").read_text()
    return after


def diff(before, after):
    text = "From: Tetris port maintainers\nSubject: [STAGING PATCH] native MT6878 MD: first-OFF and bounded restart owner\n\n"
    text += "Not shipping. Requires guarded final-producer markers and the actual\ncompleted boot transaction. Consumer remains disabled. First-OFF additionally\nrequires separate paired empty intent/final markers and persistent no-idle,\nno-sleep, no-hotplug and no-kexec kernel profile. Separate restart staging\nretains TOP/rail resources after OFF and stops at the missing execution-inhibit\nowner before regulator acquisition or ON writes. Callbacks remain vetoed.\nFailed operations retain the boot-lifetime owner and first errno; no retry.\n\n"
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
        "previous_first_off_validation": {
            "basis": "user-supplied CI result; not rerun or applied to this new revision",
            "run": "CI38315490334",
            "result": "native full vmlinux passed KUNIT=y and KUNIT=n",
            "patch_sha256": "715d68ba00491324752ddc8fe8c08e176422edf21645f3d78842bed41c82bc6a",
            "helper_sha256": "134f17d3a59f1290778b1c4f4c6faa9f526f34461f5e74b514962eaebe2d69fc",
            "production": "r182 remains unchanged",
        },
        "pins": {
            "linux": "d84b264a54a37611f2f46bc19363cb9b41606205",
            "vendor": "ee2be53cb75670b548948636a0db1d1ff112bf12",
            "installed_uboot_source_basis": "8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5",
            "parent_personal_producer_source_reviewed_not_assumed_installed": "e2a916b716c593840291aad2e03de103bdb57e7d",
        },
        "patch": {"path": "native-on-adoption.patch", "sha256": digest(patch.encode())},
        "canonical_helper": {"path": "mt6878-modem-adopt.h", "target": ADOPT,
                             "sha256": digest(after[ADOPT].encode())},
        "restart_helpers": [
            {"path": path.removeprefix(PREFIX), "target": path,
             "sha256": digest(after[path].encode())} for path in (RESTART, RESTART_TEST)
        ],
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
        "first_off": {
            "scope": "supplier-init-only native MD MTCMOS OFF readback; not full vendor rail/TOP/FLIGHT shutdown; consumer disabled; callbacks veto",
            "chosen_empty": "/chosen/tetris,modem-first-off-diagnostic",
            "supplier_empty_final_only": "nothing,modem-first-off-diagnostic",
            "producer_source": "322cf227f2ea26a7e319d20e3ce0321db8a38f15",
            "producer_status": "personal U-Boot source reviewed; paired final marker implemented; CI evidence tracked separately; installation not assumed",
            "base_config_fragment": "diagnostic.config",
            "config_fragment": "first-off.config",
            "required_resolved_config": dict.fromkeys(
                ("CPU_IDLE", "ARM_PSCI_CPUIDLE", "ARM_PSCI_CPUIDLE_DOMAIN",
                 "SUSPEND", "HIBERNATION", "HIBERNATE_CALLBACKS", "PM_SLEEP", "PM_SLEEP_SMP",
                 "HOTPLUG_CPU", "MTK_DVFSRC", "ARM_PSCI_CHECKER", "KVM", "VIRTUALIZATION",
                 "KEXEC", "KEXEC_FILE", "KEXEC_CORE"), "n"),
            "ci_merge": "merge ci.required_resolved_config with this map before olddefconfig; assert resolved union in both joint KUNIT=y/n builds so first-OFF writers are compiled",
            "order": ["revalidate actual handoff, NOMAP reservations, maps and complete ON",
                      "retain one boot takeover owner before first write",
                      "IFR9 protect/ACK", "IFR11 protect/ACK", "NEMI6:7 protect/ACK",
                      "clear PWR_ON only", "poll both ACKs and PWR_ON off",
                      "set external isolation3", "gen6299 settle >=4ms", "read all five OFF registers",
                      "mark FIRST_OFF_COMPLETE then pm_genpd_init(true)"],
            "failure": "first errno returned directly; no publication or rollback; NOMAP, persistent syscon handles and non-devm owner/device/node references retained; no reattempt before reboot",
            "publication_failure": "same retained first-error record covers generic supplier probe publication unwind",
            "runtime_put": "not used; no swallowed genpd callback errno",
            "status": "prior first-OFF baseline native CI passed per user; changed staged revision CI pending; hardware untested",
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
        "inhibited_restart": {
            "scope": "opt-in supplier-init operation after verified first-OFF; disabled consumer; no genpd publication on failure",
            "chosen_empty": "/chosen/tetris,modem-inhibited-restart-staging",
            "supplier_empty_final_only": "nothing,modem-inhibited-restart-staging",
            "producer_status": "new staging selector contract; parent producer implementation not assumed",
            "profile": "same resolved diagnostic.config plus first-off.config; no additional active hardware permission",
            "order": ["retain existing boot takeover identity under boot-lock then owner-lock",
                      "claim exactly one restart attempt", "revalidate paired selectors and disabled modem",
                      "revalidate actual unchanged handoff/NOMAP/maps", "read complete native OFF",
                      "retain DT TOP node and cached native syscon map",
                      "retain three distinct actual available rail nodes and exact pinned voltage pairs",
                      "stop at missing execution-inhibit owner before regulator_get and every ON operation"],
            "resource_profile": {"power_flow_config": "absent or exact zero",
                                 "rails_uv": {"md-vmodem": [800000, 800000],
                                              "md-vsram": [800000, 800000],
                                              "md-vdigrf": [700000, 700000]}},
            "boundary_errno": "-EOPNOTSUPP; earlier exact errno wins, including -EPROBE_DEFER",
            "retention": "non-devm first-OFF owner/supplier/modem, NOMAP, persistent maps and all acquired TOP/rail node references survive probe unwind through reboot",
            "not_claimed": ["exclusive ownership of shared rails/TOP", "regulator handles",
                            "execution-inhibited ON", "new authentication/EMI permission",
                            "full shutdown", "consumer/transport activation"],
            "tests": {"static": "test_static.py", "kunit_suite": "mt6878-md-inhibited-restart-owner",
                      "kunit_scope": "actual admission/first-errno helpers and genpd callback veto; no hardware operations",
                      "execution": "not compiled or executed locally; new revision native KUNIT=y/n CI pending"},
            "evidence": "RESTART-SOURCE-EVIDENCE.json",
            "status": "resource-operation-implemented; active-inhibit-owner-missing; hardware-untested",
        },
        "failed_requirements": {
            "consumer_unbind_veto": "detach_dev is void and cannot veto; detach retires observation with ESHUTDOWN, no teardown claim",
            "dynamic_supplier_removal": "existing suppress_bind_attrs only prevents userspace unbind; arbitrary in-kernel unregister unsupported",
            "present_packaged_config_runtime_adoption": "blocked by OF_DYNAMIC=y and MEMORY_HOTREMOVE=y; package unchanged",
        },
        "remaining": ["new staged revision native KUNIT=y/n CI and matched-candidate first-OFF hardware validation",
                      "consumer activation/attachment", "active execution-inhibit owner before ON",
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
        if any((args.prepared_kernel / path).exists() for path in (ADOPT, RESTART, RESTART_TEST)):
            raise ValueError("prepared kernel already contains a staging helper")
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
        print("PASS: exact packaged MD stack, deterministic first-OFF/restart patch and exact Git context application")
        print("inputs=" + str(len(inputs)) + "; patch_sha256=" + digest(patch.encode()))


if __name__ == "__main__":
    main()
