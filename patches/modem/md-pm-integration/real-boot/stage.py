#!/usr/bin/env python3
"""Check the real post-r184 frozen native sources; no compilation or installation."""

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
FROZEN = "cbb777d415b564c1e40598740288c0c9d953e745"
POST_OFF = "06fa22493cb8686e67c82236fdd26741e8da0378"
PREFIX = "drivers/pmdomain/mediatek/"
ADOPT = PREFIX + "mt6878-modem-adopt.h"
CFILE = PREFIX + "mtk-pm-domains.c"
KCONFIG = PREFIX + "Kconfig"
PATCH = HERE / "native-real-boot-post-off.patch"
BASE_PATCH = "patches/modem/md-pm-integration/native-on-adoption.patch"
BASE_SHA = "715d68ba00491324752ddc8fe8c08e176422edf21645f3d78842bed41c82bc6a"
TOP_SHA = "d6edccda312bf133173e629aba23d7f2dc3a578b22a8b710d65d1ec17f8b8ff5"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


native = module("real_boot_native_stage", HERE.parent / "stage.py")
parent = module("real_boot_image_stage", REPO / "ci/stage-native-modem-image.py")
wakeup = module("real_boot_wakeup_stage", REPO / "ci/stage-native-wakeup-image.py")


def object_bytes(revision, path):
    return subprocess.check_output(["git", "-C", str(REPO), "show", revision + ":" + path])


def frozen_top():
    data = object_bytes(POST_OFF, "patches/modem/md-pm-integration/post-off/mt6878-modem-post-off.h")
    require(digest(data) == TOP_SHA, "frozen TOP helper changed")
    return data.decode()


def baseline(kernel, output):
    _, inputs = native.packaged(kernel, output)
    data = object_bytes(FROZEN, BASE_PATCH)
    require(digest(data) == BASE_SHA, "actual image's frozen MD patch changed")
    native.apply(output, data.decode())
    # Kconfig is taken from the same checksum-verified d84 source as pm-domain C.
    config = (kernel / KCONFIG).read_bytes()
    evidence = json.loads((HERE / "SOURCE-EVIDENCE.json").read_text())
    require(evidence["pins"]["linux"] == LINUX and digest(config) ==
            evidence["sources"]["linux:" + KCONFIG]["sha256"], "not pristine d84 Kconfig")
    (output / KCONFIG).write_bytes(config)
    def sections(data, paths):
        return "".join(section for section in re.split(r"(?=^diff --git )", data, flags=re.M)
                       if any(section.startswith("diff --git a/" + path + " b/" + path + "\n")
                              for path in paths))
    # Reproduce packaged Kconfig changes without pulling unrelated source files.
    names = list(dict.fromkeys(re.findall(r"^\s+([\w.-]+\.patch)$",
        (native.PACKAGE / "APKBUILD").read_text(), re.M)))
    for name in names:
        selected = sections((native.PACKAGE / name).read_text(encoding="latin-1"), {KCONFIG})
        if selected:
            native.apply(output, selected)
    # Include the image's real shared-provider layout before generating C hunks.
    camera = "patches/camera-camisp/native-integration/native-provider-after-md.patch"
    data = object_bytes(FROZEN, camera)
    require(digest(data) == "34845f753bdd21af7444f8e1bc5de8ca887a007a707463972a90c65211c9c99d",
            "frozen image shared provider changed")
    native.apply(output, sections(data.decode(), {CFILE, KCONFIG}))
    native.apply(output, parent.modem_ack_patch())
    native.apply(output, wakeup.patch_text(parent))
    before = {path: (output / path).read_text() for path in (ADOPT, KCONFIG, CFILE)}
    require("#define MT6878_MD_ACK BIT(30)" in
            (output / (PREFIX + "mt6878-modem-pm.h")).read_text(), "missing real ACK30 profile")
    return before, inputs


def candidate(before):
    after = dict(before)
    marker = "static int mt6878_md_adopt_revalidate(struct scpsys_domain *pd,"
    end_marker = "static int mt6878_md_first_off_profile("
    start = after[ADOPT].index(marker)
    end = after[ADOPT].index(end_marker, start)
    original = after[ADOPT][start:end]
    physical_on = "\tif (!ret)\n\t\tret = mt6878_md_adopt_on(pd, now.on);\n"
    require(original.count(physical_on) == 1, "wrong frozen resource/ON validation split")
    resources = original.replace("mt6878_md_adopt_revalidate(",
                                 "mt6878_md_adopt_revalidate_resources(", 1)
    resources = resources.replace(physical_on, "", 1)
    on_wrapper = ("static int mt6878_md_adopt_revalidate(struct scpsys_domain *pd,\n"
                  "\t\t\t\t     struct mt6878_md_adoption *owner)\n"
                  "{\n\tu32 on[5];\n\tint ret;\n\n"
                  "\tret = mt6878_md_adopt_revalidate_resources(pd, owner);\n"
                  "\tif (!ret)\n\t\tret = mt6878_md_adopt_on(pd, on);\n"
                  "\treturn ret;\n}\n\n")
    # Post-OFF callers still verify immutable handoff/reservations/maps, but
    # must use their separate real OFF/ON readback rather than require ON here.
    after[ADOPT] = after[ADOPT][:start] + resources + on_wrapper + after[ADOPT][end:]
    anchor = "static void mt6878_md_first_off_publication_fault("
    require(before[ADOPT].count(anchor) == 1, "wrong frozen supplier hook")
    after[ADOPT] = after[ADOPT].replace(anchor,
        '#include "mt6878-modem-real-boot.h"\n\n' + anchor, 1)
    hook = ("\tif (!ret) {\n\t\towner->state = MT6878_MD_OBSERVED_ON;\n"
            "\t\tif (first_off)\n\t\t\tret = mt6878_md_first_off(pd, owner);\n\t}\n")
    require(after[ADOPT].count(hook) == 1, "missing actual first-OFF return boundary")
    after[ADOPT] = after[ADOPT].replace(hook, hook +
        "\tif (!ret && IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING))\n"
        "\t\tret = mt6878_md_real_boot_post_off(pd, owner);\n", 1)
    status = ("\tret = mt6878_md_adopt_property(modem, \"status\", status, sizeof(status));\n"
              "\tif (ret || memcmp(status, \"disabled\", sizeof(status))) {\n"
              "\t\tof_node_put(modem);\n\t\treturn ret ? ret : -EBUSY;\n\t}\n")
    require(after[ADOPT].count(status) == 1, "missing real consumer activation boundary")
    after[ADOPT] = after[ADOPT].replace(status,
        "\tif (IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING) &&\n"
        "\t    of_device_is_available(modem)) {\n\t\tret = 0;\n\t} else {\n" +
        "".join("\t" + line if line.strip() else line for line in status.splitlines(True)) +
        "\t}\n", 1)
    after[ADOPT] = after[ADOPT].replace(
        "MD adoption detached; physical ON retained, reattach/start unsupported",
        "MD adoption detached; physical state unchanged, resources retained, reboot required")
    after[CFILE] = native.replace_once(before[CFILE],
        "\t\tpd->genpd.power_on = mt6878_md_adopt_transition;",
        "\t\tpd->genpd.power_on = IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING) ?\n"
        "\t\t\tmt6878_md_real_boot_power_on : mt6878_md_adopt_transition;")
    after[CFILE] = native.replace_once(after[CFILE],
        "\t\tpd->genpd.attach_dev = mt6878_md_adopt_attach;",
        "\t\tpd->genpd.attach_dev = IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING) ?\n"
        "\t\t\tmt6878_md_real_boot_attach : mt6878_md_adopt_attach;")
    require(before[KCONFIG].count("endmenu\n") == 1, "ambiguous MediaTek Kconfig")
    after[KCONFIG] = before[KCONFIG].replace("endmenu\n",
        'source "drivers/pmdomain/mediatek/mt6878-modem-post-off.Kconfig"\n'
        'source "drivers/pmdomain/mediatek/mt6878-modem-real-boot.Kconfig"\n\nendmenu\n')
    after[PREFIX + "mt6878-modem-real-boot.h"] = (HERE / "mt6878-modem-real-boot.h").read_text()
    after[PREFIX + "mt6878-modem-real-boot.Kconfig"] = (HERE / "Kconfig").read_text()
    after[PREFIX + "mt6878-modem-post-off.h"] = frozen_top()
    after[PREFIX + "mt6878-modem-post-off.Kconfig"] = object_bytes(POST_OFF,
        "patches/modem/md-pm-integration/post-off/Kconfig").decode()
    return after


def diff(before, after):
    result = ("Subject: [STAGING PATCH] MT6878 MD: wire real native genpd ON from first-OFF\n\n"
              "Apply after frozen native MD/shared-provider, ACK30 and0187 wakeup.\n"
              "Default off. Submit real FLIGHT(true), check only defined a0 using the\n"
              "matched ATF inner contract, then check TOP. No UFS calibration provider\n"
              "is allowed. Admit the sole genuine CCCI consumer from OFF and execute\n"
              "voltage/sync, TOP ungate, FLIGHT(false), isolation/PWR_ON/ACK30, reverse\n"
              "bus release and actual ON readback. No invented execution-inhibit gate.\n"
              "POWER/0, transport and lifecycle are separate, unvalidated operations.\n\n")
    for path in sorted(after):
        if before.get(path) == after[path]:
            continue
        result += "diff --git a/" + path + " b/" + path + "\n"
        if path not in before:
            result += "new file mode 100644\n"
        result += "".join(difflib.unified_diff(before.get(path, "").splitlines(True),
            after[path].splitlines(True), fromfile="a/" + path if path in before else "/dev/null",
            tofile="b/" + path))
    return result


def apply(tree, data, check=False):
    result = subprocess.run(["git", "apply", "--verbose", "--whitespace=error"] +
        (["--check"] if check else []) + ["-"], input=data, cwd=tree, text=True,
        capture_output=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE)})
    require(result.returncode == 0 and "Skipped patch" not in result.stderr,
            "real-boot patch failed: " + result.stdout + result.stderr)
    require(not re.search(r"\boffset\b|\bfuzz\b", result.stderr), "patch used offset/fuzz")
    for path in re.findall(r"^\+\+\+ b/(\S+)$", data, re.M):
        require("Checking patch " + path in result.stderr, "patch did not check " + path)


def validate(kernel, emit=False):
    if not emit:
        manifest = json.loads((HERE / "STAGING.json").read_text())
        for name, expected in manifest["files_sha256"].items():
            require(digest((HERE / name).read_bytes()) == expected,
                    "real-boot staged input differs from manifest: " + name)
    # Disposable text-only source copies; never modify the input kernel.
    with tempfile.TemporaryDirectory(prefix=".apply-", dir=HERE) as directory:
        tree = Path(directory)
        before, inputs = baseline(kernel, tree)
        after = candidate(before)
        expected = diff(before, after)
        if emit:
            return expected
        data = PATCH.read_text()
        require(data == expected, "generated integration delta is stale")
        apply(tree, data, check=True)
        apply(tree, data)
        for path, source in after.items():
            require((tree / path).read_text() == source, "applied source differs: " + path)
        # OFF lifecycle stays unsupported; the new ON is wired to actual genpd.
        body = (tree / ADOPT).read_text()
        require("ret = owner->first_error ? owner->first_error : -EOPNOTSUPP;" in body,
                "unsupported OFF transition no longer vetoed")
        require("mt6878_md_real_boot_power_on : mt6878_md_adopt_transition" in after[CFILE] and
                "mt6878_md_real_boot_attach : mt6878_md_adopt_attach" in after[CFILE],
                "new native ON/admission callbacks are not wired")
        return {"patch_sha256": digest(data.encode()), "base": FROZEN,
                "ack": "BIT(30)", "packaged_inputs": inputs,
                "modified": sorted(after), "validation": "static git apply check + application only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=REPO.parent / ("linux-" + LINUX))
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    result = validate(args.kernel, args.emit)
    if args.emit:
        print(result, end="")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
