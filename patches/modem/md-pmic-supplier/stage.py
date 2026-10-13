#!/usr/bin/env python3
"""Generate/check an additive MT6363 modem supplier patch; never compile."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
DRIVER = "drivers/regulator/mt6363-regulator.c"
BINDING = "Documentation/devicetree/bindings/regulator/mediatek,mt6363-regulator.yaml"
HELPER = "drivers/regulator/mt6363-modem-regulator.h"
TEST = "drivers/regulator/mt6363-modem-regulator-test.h"
DT = "arch/arm64/boot/dts/mediatek/mt6878-modem-pmic-disabled.dtsi"
PATCH = HERE / "native-modem-rails.patch"
FILES = {DRIVER, BINDING}
INPUT_HASHES = {
    "0008-connectivity-mt6878-mt6631-connsys.patch": "02c72385dc0d08367299d0b55d7e50eecdc4145748c6af025243e44ab1dda32c",
    "0030-regulator-mediatek-mt6878-gpu-rails.patch": "330e46826a6cc167c93fb0b029b458d798435b1bf33a076d774cab807341da38",
}
BEFORE_HASHES = {
    DRIVER: "62f4f1ed120a05aab237b46be84be8c965ba076a0baee8d85cbefa75aced8dfb",
    BINDING: "9baee35afefe2ed8b00e8165992ba879c3eaeceb1662230098e19823a5df88ab",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sections(text):
    headers = list(re.finditer(r"^--- (?:a/\S+|/dev/null)\n\+\+\+ b/(\S+)\n", text, re.M))
    for index, match in enumerate(headers):
        if match[1] not in FILES:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        yield text[match.start():end].split("\ndiff --git ")[0].split("\n-- \n")[0] + "\n"


def apply(tree, patch, check=False):
    command = ["git", "apply", "--verbose", "--whitespace=nowarn"]
    if check:
        command.append("--check")
    result = subprocess.run(command + ["-"], input=patch, text=True, cwd=tree,
                            capture_output=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE)})
    if result.returncode or "Skipped patch" in result.stderr:
        raise ValueError(result.stdout + result.stderr)
    for path in re.findall(r"^\+\+\+ b/(\S+)$", patch, re.M):
        if "Checking patch " + path not in result.stderr:
            raise ValueError("patch matcher skipped " + path)


def packaged(tree):
    kernel = ROOT.parent / ("linux-" + LINUX)
    if (kernel / DRIVER).exists():
        raise ValueError("expected pristine d84 without an MT6363 regulator driver")
    names = list(dict.fromkeys(re.findall(r"^\s+([\w.-]+\.patch)$", (PACKAGE / "APKBUILD").read_text(), re.M)))
    inputs = []
    for name in names:
        raw = (PACKAGE / name).read_bytes()
        selected = "".join(sections(raw.decode("latin-1")))
        if selected:
            if name not in INPUT_HASHES or digest(raw) != INPUT_HASHES[name]:
                raise ValueError("packaged input changed; re-review " + name)
            apply(tree, selected)
            inputs.append({"patch": name, "sha256": digest(raw)})
    expected = ["0008-connectivity-mt6878-mt6631-connsys.patch", "0030-regulator-mediatek-mt6878-gpu-rails.patch"]
    if [item["patch"] for item in inputs] != expected:
        raise ValueError("packaged minimal provider ordering changed; re-review before staging")
    before = {path: (tree / path).read_text() for path in FILES}
    for path, value in before.items():
        if digest(value.encode()) != BEFORE_HASHES[path]:
            raise ValueError("exact packaged minimal source differs: " + path)
    return before, inputs


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("packaged source anchor missing/ambiguous: " + old)
    return text.replace(old, new, 1)


def candidate(before):
    after = dict(before)
    source = replace_once(before[DRIVER], "static int mt6363_regulator_probe(",
                          '#include "mt6363-modem-regulator.h"\n\nstatic int mt6363_regulator_probe(')
    source = replace_once(source, "\treturn 0;\n}\n\nstatic const struct of_device_id",
                          "\treturn mt6363_md_register(pdev, regmap);\n}\n\nstatic const struct of_device_id")
    source += '\n#include "mt6363-modem-regulator-test.h"\n'
    after[DRIVER] = source
    properties = ""
    for name in ("vbuck1", "vbuck2", "vsram-modem"):
        properties += f"  {name}:\n    type: object\n    $ref: regulator.yaml#\n    unevaluatedProperties: false\n\n"
    after[BINDING] = replace_once(before[BINDING], "required:\n", properties + "required:\n")
    for target in (HELPER, TEST, DT):
        after[target] = (HERE / Path(target).name).read_text()
    return after


def diff(before, after):
    output = "From: Tetris port maintainers\nSubject: [STAGING PATCH] regulator: MT6363 native modem rails\n\n"
    output += ("Add source-backed VBUCK1/2 and VSRAM_MODEM to the exact packaged\n"
               "minimal provider. Existing connectivity blocks remain byte-identical.\n"
               "New children must be available to register; metadata remains disabled\n"
               "and is not included by any shipping DT. Preserve inherited control\n"
               "banks and enable requests. Main selector readback is not DA voltage.\n"
               "Shared-key FCCM changes, voter takeover and set_load stay unsupported.\n\n")
    for path in sorted(after):
        if before.get(path) == after[path]:
            continue
        output += "diff --git a/" + path + " b/" + path + "\n"
        if path not in before:
            output += "new file mode 100644\n"
        output += "".join(difflib.unified_diff(before.get(path, "").splitlines(True), after[path].splitlines(True),
                                          fromfile="a/" + path if path in before else "/dev/null", tofile="b/" + path))
    return output


def validate(emit=False):
    with tempfile.TemporaryDirectory(prefix=".source-check-", dir=HERE) as temp:
        tree = Path(temp)
        before, inputs = packaged(tree)
        after = candidate(before)
        generated = diff(before, after)
        if not emit and PATCH.read_text() != generated:
            raise ValueError("patch differs from canonical sources/generator")
        apply(tree, generated, check=True)
        apply(tree, generated)
        for path, expected in after.items():
            if (tree / path).read_text() != expected:
                raise ValueError("actual application differs: " + path)
        return generated, before, after, inputs


def contract(patch, before, after, inputs):
    return {
        "schema": 1, "phase": "additive-native-provider-source-only-not-shipping",
        "pins": {"linux": LINUX, "vendor": VENDOR},
        "live_basis": "parent-measured boot b8e13a10-19f6-4ab7-9f71-de0623e1d494 exposes only mt6363-vcn13 and mt6363-vrfio18 in sysfs; source worker did not access phone",
        "packaged_inputs": inputs,
        "prepared_before_sha256": {path: digest(data.encode()) for path, data in sorted(before.items())},
        "staged_after_sha256": {path: digest(data.encode()) for path, data in sorted(after.items())},
        "patch": {"path": PATCH.name, "sha256": digest(patch.encode())},
        "canonical_sources": [Path(path).name for path in (HELPER, TEST, DT)],
        "stock_consumer_mapping": {"md-vmodem": {"rail": "vbuck2", "microvolt": 800000},
                                   "md-vsram": {"rail": "vsram-modem", "microvolt": 800000},
                                   "md-vdigrf": {"rail": "vbuck1", "microvolt": 700000}},
        "selector_semantics": "source-defined main RG selector with checked normal AP OP_EN/OP_CFG and SSHUB exclusion; programmed selector is not independent DA voltage measurement",
        "ownership": "mutex serializes these three native rails; preserve OP banks/SSHUB/shared key; checks do not prove global secure actor exclusion; inherited enables cannot be disabled",
        "registration": "actual available unique native DT children only; exact DT node/init data; mutation callbacks reject core probe-time changes; no new allocation/PMIC access when all three are unavailable",
        "supported": ["standard linear list/map", "guarded main selector get/set with readback",
                      "guarded exact SET/CLR enable aliases and SW request readback", "observe source-defined FCCM/HW-LP mode",
                      "guarded NORMAL/IDLE LP-bit changes with source 100us IDLE exit delay"],
        "denied": ["independent DA voltage/power-good status (not defined by pinned source)",
                   "SSHUB selector takeover", "OP_EN/OP_CFG hardware voter rewrite", "shared-key FCCM/FAST changes and exit from inherited FAST",
                   "STANDBY/ULP", "set_load/DRMS", "suspend controls", "calibration/efuse/unlock",
                   "unknown ramp rate or invented voltage/settle helpers", "probe-time clamp/enable/mode", "inherited enable teardown"],
        "failure": "first hardware write/post-write errno latched per rail; no compensating writes or unsafe retry; read-only errors returned directly",
        "parser_limit": "standard of_get_regulator_init_data returns NULL without an errno; reject as EINVAL instead of core unconstrained fallback",
        "metadata": {"path": DT, "included": False, "children": "all disabled; no modem consumer supply wiring or activation"},
        "checks": {"source": "python3 -B patches/modem/md-pmic-supplier/stage.py",
                   "tests": "python3 -B patches/modem/md-pmic-supplier/test_static.py",
                   "native_target": "drivers/regulator/mt6363-regulator.o",
                   "kunit_suite": "mt6363-native-modem-regulator", "native": "not compiled or executed; parent ARM64 integration pending"},
        "hardware": "untested; no phone access, regulator operation or modem activation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true", help="regenerate local staging patch, hashes and pinned evidence")
    parser.add_argument("--prepared-kernel", type=Path)
    parser.add_argument("--ci-apply", action="store_true")
    args = parser.parse_args()
    if args.ci_apply and (not args.prepared_kernel or args.emit or
                         os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true"):
        parser.error("--ci-apply requires a prepared kernel and GitHub CI; no local native builds")
    patch, before, after, inputs = validate(emit=args.emit)
    if args.prepared_kernel:
        for path, data in before.items():
            if (args.prepared_kernel / path).read_text() != data:
                raise ValueError("actual prepared provider differs: " + path)
        for path in set(after) - set(before):
            if (args.prepared_kernel / path).exists():
                raise ValueError("prepared provider already contains modem rail input: " + path)
        if args.ci_apply:
            apply(args.prepared_kernel, patch, check=True)
            apply(args.prepared_kernel, patch)
            for path, data in after.items():
                if (args.prepared_kernel / path).read_text() != data:
                    raise ValueError("actual staged regulator source differs: " + path)
    manifest = json.dumps(contract(patch, before, after, inputs), indent=2) + "\n"
    if args.emit:
        import audit_source
        evidence = json.dumps(audit_source.evidence(), indent=2) + "\n"
        PATCH.write_text(patch)
        (HERE / "STAGING.json").write_text(manifest)
        (HERE / "SOURCE-EVIDENCE.json").write_text(evidence)
    elif (HERE / "STAGING.json").read_text() != manifest:
        raise ValueError("staging hashes/contract differ")
    print("PASS: exact packaged minimal provider, deterministic additive patch and exact Git application")
    print("patch_sha256=" + digest(patch.encode()))


if __name__ == "__main__":
    main()
