#!/usr/bin/env python3
"""Compose/compile real ON in CI on a disposable prepared kernel, never an image."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import tempfile

import stage

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CONTRACT = HERE / "CI-SOURCES.json"
OBJECTS = ("drivers/pmdomain/mediatek/mtk-pm-domains.o",
           "drivers/regulator/mt6363-regulator.o")
DTB = "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native-md-first-off.dtb"
MD_PATHS = (stage.CFILE, stage.ADOPT, stage.KCONFIG,
            stage.PREFIX + "mt6878-modem-pm.h", stage.PREFIX + "mtk-pm-domains.h")
REQUIRED = ("ARM64", "ARCH_MEDIATEK", "HAVE_ARM_SMCCC", "OF", "PM", "MFD_SYSCON",
            "REGULATOR", "MFD_MT6363", "REGULATOR_MT6363",
            "REGMAP_SPMI", "MTK_SCPSYS_PM_DOMAINS", "MTK_MT6878_NATIVE_VMM",
            "PM_SLEEP", "PM_SLEEP_SMP", "SUSPEND", "HOTPLUG_CPU")
DISABLED = ("CPU_IDLE", "HIBERNATION", "OF_OVERLAY", "OF_UNITTEST", "OF_DYNAMIC",
            "MEMORY_HOTREMOVE", "MTK_DVFSRC", "ARM_PSCI_CHECKER", "KVM",
            "KEXEC", "KEXEC_FILE", "KEXEC_CORE", "KUNIT", "SCSI_UFS_MEDIATEK_DBG")
REAL = ("MTK_MT6878_MODEM_REAL_BOOT_STAGING", "MTK_MT6878_MODEM_POST_OFF_TOP_STAGING")


def module(name, relative):
    path = REPO / relative
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def require_ci():
    stage.require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true"
                  and platform.system() == "Linux", "native preparation/build is Linux GitHub CI-only")


def isolated(path):
    path = Path(os.path.abspath(path))
    stage.require(path.resolve() == path, "CI path must not traverse symlinks")
    frozen = Path(os.environ.get("TETRIS_NATIVE_SOURCE_TREE", REPO)).resolve()
    for root in {REPO.resolve(), frozen}:
        stage.require(path != root and path not in root.parents, "CI path overlaps source checkout")
        if root in path.parents:
            stage.require(REPO / "out" in path.parents and root == REPO,
                          "CI mutation requires an isolated out/ copy or external work directory")
    return path


def recipes():
    # These unchanged tracked helpers implement the actual r188 package chain.
    gnss = module("real_on_gnss_image", "ci/stage-native-gnss-image.py")
    tx = gnss.helper()
    tx_data, tx_manifest = tx.inputs()
    parent = tx.parent_stage()
    rails = module("real_on_native_rails", "ci/stage-native-modem-rails.py")
    rail_data, rail_manifest, _ = rails.inputs()
    prefix = [
        ("0180-native-md-first-off.patch", parent.frozen(stage.BASE_PATCH)),
        ("0181-native-camera-after-md.patch", parent.frozen(
            "patches/camera-camisp/native-integration/native-provider-after-md.patch")),
        ("0182-native-md-first-off-board.patch", parent.dt_patch().encode()),
        ("0183-native-camera-header-parent.patch", parent.native_header_patch().encode()),
        ("0184-native-modem-single-ack.patch", parent.modem_ack_patch().encode()),
        (stage.wakeup.PATCH, stage.wakeup.patch_text(parent).encode()),
    ]
    delta = [(rails.DRIVER_PATCH, rail_data),
             (rails.DT_PATCH, rails.integration_patch(activate=False)),
             ("0188-native-modem-real-on.patch", stage.PATCH.read_bytes())]
    return prefix, delta, rails, rail_manifest, {
        "source_profile": tx.PROFILE + "-wakeup", "kernel_package": "7.2.1-r188",
        "gnss_patch": tx.PATCH, "gnss_patch_sha512": hashlib.sha512(tx_data).hexdigest(),
        "connectivity_commit": tx_manifest["connectivity_commit"],
        "gnss_scope": "exact1009 belongs to external connectivity sources, not native MD translation units",
    }


def source_contract(pristine):
    """Generate source hashes from exact text-only r188 reconstruction."""
    with tempfile.TemporaryDirectory(prefix=".ci-inputs-", dir=HERE) as directory:
        root = Path(directory)
        packaged = root / "packaged"
        _, inputs = stage.native.packaged(pristine, packaged)
        config = packaged / stage.KCONFIG
        config.write_bytes((pristine / stage.KCONFIG).read_bytes())
        names = list(dict.fromkeys(re.findall(r"^\s+([\w.-]+\.patch)$",
            (stage.native.PACKAGE / "APKBUILD").read_text(), re.M)))
        for name in names:
            raw = (stage.native.PACKAGE / name).read_text(encoding="latin-1")
            selected = "".join(part for part in re.split(r"(?=^diff --git )", raw, flags=re.M)
                if part.startswith("diff --git a/" + stage.KCONFIG + " b/" + stage.KCONFIG + "\n"))
            if selected:
                stage.native.apply(packaged, selected)
        r188 = root / "r188"
        stage.baseline(pristine, r188)
        prefix, delta, _, _, profile = recipes()
        return {"schema": 1, "profile": profile, "linux": stage.LINUX,
                "packaged_inputs": inputs,
                "helper_sha256": {path: stage.digest((REPO / path).read_bytes()) for path in (
                    "ci/stage-native-modem-image.py", "ci/stage-native-gnss-image.py",
                    "ci/stage-gnss-tx-image.py", "ci/stage-native-wakeup-image.py",
                    "ci/stage-native-modem-rails.py")},
                "patches_sha256": {name: stage.digest(data) for name, data in prefix + delta},
                "prepared_before_sha256": {name: {path: stage.digest((tree / path).read_bytes())
                    for path in MD_PATHS if (tree / path).is_file()}
                    for name, tree in (("packaged", packaged), ("r188", r188))},
                "compilation": "not performed by source-contract generation"}


def check(kernel, input_profile):
    """Static prepared-source check, permitted locally; never writes or compiles."""
    kernel = Path(kernel).resolve()
    contract = json.loads(CONTRACT.read_text())
    for path, expected in contract["helper_sha256"].items():
        stage.require(stage.digest((REPO / path).read_bytes()) == expected,
                      "r188/rails helper changed; re-review ordering: " + path)
    prefix, delta, rails, rail_manifest, profile = recipes()
    observed = {name: stage.digest(data) for name, data in prefix + delta}
    stage.require(observed == contract["patches_sha256"], "CI recipe differs from reviewed source snapshot")
    stage.require(input_profile in ("packaged", "r188"), "choose explicit packaged or r188 input")
    for relative, expected in contract["prepared_before_sha256"][input_profile].items():
        path = kernel / relative
        stage.require(path.resolve() == path and path.is_file() and stage.digest(path.read_bytes()) == expected,
                      "prepared " + input_profile + " source differs: " + relative)
    for relative, expected in rail_manifest["prepared_before_sha256"].items():
        stage.require(stage.digest((kernel / relative).read_bytes()) == expected,
                      "actual packaged MT6363 provider differs: " + relative)
    if input_profile == "r188":
        stage.require((kernel / (stage.PREFIX + "mt6878-modem-pm.h")).read_text().count(
            "#define MT6878_MD_ACK BIT(30)") == 1, "missing ACK30 correction")
        source = (kernel / stage.ADOPT).read_text()
        for needle in ("register_pm_notifier(&mt6878_md_sleep_notifier)", "cpu_hotplug_disable();",
                       "mutex_trylock(&system_transition_mutex)", "!IS_ENABLED(CONFIG_PM_SLEEP)"):
            stage.require(needle in source, "0187 wakeup owner/order absent: " + needle)
        rails.check_kernel(kernel, activate=False)
    return prefix, delta, profile


def apply_source(kernel, data, strict=False, check_only=False):
    # Stop Git discovery at the disposable kernel's parent, including out/
    # copies below a checkout. Do not inherit a misleading repository prefix.
    command = ["git", "apply", "--verbose", "--whitespace=" + ("error" if strict else "nowarn")]
    if check_only:
        command.append("--check")
    result = subprocess.run(command + ["-"], cwd=kernel, input=data, capture_output=True,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(kernel.parent)})
    output = result.stderr.decode()
    stage.require(result.returncode == 0 and "Skipped patch" not in output,
                  "CI source application failed: " + output)
    for path in re.findall(r"^\+\+\+ b/(\S+)$", data.decode(), re.M):
        stage.require("Checking patch " + path in output, "CI application skipped " + path)
    if strict:
        stage.require(not re.search(r"\boffset\b|\bfuzz\b", output), "real ON delta used offset/fuzz")


def prepare(kernel, input_profile, enable_real_on=False):
    require_ci()
    stage.require(enable_real_on is True, "real ON source staging requires explicit --enable-real-on")
    kernel = isolated(kernel)
    prefix, delta, profile = check(kernel, input_profile)
    patches = (prefix if input_profile == "packaged" else []) + delta
    for _, data in patches:
        for relative in re.findall(r"^\+\+\+ b/(\S+)$", data.decode(), re.M):
            path = kernel / relative
            stage.require(path.resolve() == path and
                          (not path.exists() or path.stat().st_nlink == 1),
                          "CI target is symlinked/hardlinked: " + relative)
    for name, data in patches:
        # Legacy frozen patches have their original whitespace/context; their
        # exact digests were checked above. The new real-ON delta is strict.
        if name == "0188-native-modem-real-on.patch":
            apply_source(kernel, data, strict=True, check_only=True)
            apply_source(kernel, data, strict=True)
        else:
            apply_source(kernel, data)
    board = kernel / ("arch/arm64/boot/dts/mediatek/" + stage.parent.BOARD + ".dts")
    source = board.read_text()
    children = (kernel / "arch/arm64/boot/dts/mediatek/mt6878-modem-pmic-disabled.dtsi").read_text()
    stage.require('&mddriver {\n\tstatus = "disabled";' in source and
                  children.count('status = "disabled";') == 3 and 'status = "okay";' not in children,
                  "compile-only board must keep the actual consumer and rail children disabled")
    return {**profile, "input_profile": input_profile,
            "applied": {name: stage.digest(data) for name, data in patches},
            "consumer": "disabled compile-only DT; no runtime activation",
            "new_sources": {relative: stage.digest((kernel / relative).read_bytes())
                for relative in (*MD_PATHS, "drivers/regulator/mt6363-regulator.c",
                                 "drivers/regulator/mt6363-modem-regulator.h")},
            "status": "source-staged; no compilation yet"}


def run(command, log):
    with log.open("ab") as stream:
        subprocess.run(list(map(str, command)), check=True, stdout=stream, stderr=subprocess.STDOUT)


def check_disabled(lines, symbols):
    # Kconfig omits some invisible n symbols instead of writing a comment.
    # Any assignment is unexpected here; y/m must never pass as disabled.
    for symbol in symbols:
        stage.require(not any(line.startswith("CONFIG_" + symbol + "=") for line in lines),
                      "CI excluded dependency has an assignment: " + symbol)


def configure(kernel, output, config, enabled, log):
    make = ["make", "-j4", "-C", str(kernel), "O=" + str(output), "ARCH=arm64", "LLVM=1"]
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(config, output / ".config")
    args = [kernel / "scripts/config", "--file", output / ".config"]
    for symbol in REQUIRED:
        args += ["--enable", symbol]
    for symbol in DISABLED:
        args += ["--disable", symbol]
    for symbol in REAL:
        args += ["--enable" if enabled else "--disable", symbol]
    run(args, log)
    run([*make, "olddefconfig"], log)
    lines = (output / ".config").read_text().splitlines()
    original = config.read_text().splitlines()
    for symbol in ("LTO_CLANG_THIN", "CFI", "CFI_PERMISSIVE"):
        for setting in ("CONFIG_" + symbol + "=y", "# CONFIG_" + symbol + " is not set"):
            if setting in original:
                stage.require(setting in lines, "CI changed the inherited compiler/security profile: " + symbol)
    for symbol in REQUIRED + (REAL if enabled else ()):
        stage.require("CONFIG_" + symbol + "=y" in lines, "CI dependency did not resolve: " + symbol)
    check_disabled(lines, DISABLED + (() if enabled else REAL))
    return make


def ir_callbacks(ir, callbacks):
    """Resolve retained pointer symbols to actual definitions, allowing LLVM suffixes/aliases."""
    symbol = r'(?:(?:"([^\"]+)")|([A-Za-z0-9_.$-]+))'
    definitions = {a or b for a, b in re.findall(r'^define\b[^\n]*@' + symbol + r'\(', ir, re.M)}
    aliases = {a or b: c or d for a, b, c, d in re.findall(
        r'^@' + symbol + r'\s*=\s*[^\n]*\balias\b[^\n]*@' + symbol, ir, re.M)}
    pointers = {a or b for a, b in re.findall(r'\bptr\s+@' + symbol, ir)}
    bindings = {}
    for name in callbacks:
        candidates = sorted(value for value in pointers if value == name or value.startswith(name + "."))
        for pointer in candidates:
            value, seen = pointer, set()
            while value in aliases and value not in seen:
                seen.add(value)
                value = aliases[value]
            if value in definitions:
                bindings[name] = {"pointer_symbol": pointer, "defined_symbol": value}
                break
        stage.require(name in bindings, "actual assigned callback not retained as defined function pointer: " + name)
    return bindings


def object_identity(path, callbacks=()):
    data = path.read_bytes()
    if data[:4] in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
        # Match the repository's shipping ThinLTO profile instead of disabling it.
        require_ci()
        ir = subprocess.check_output(["llvm-dis", "-o", "-", str(path)], text=True)
        triples = re.findall(r'^target triple = "([^"]+)"$', ir, re.M)
        stage.require(len(triples) == 1 and triples[0].startswith("aarch64-"), "wrong LLVM target architecture")
        bindings = ir_callbacks(ir, callbacks)
        return {"sha256": stage.digest(data), "size": len(data), "format": "LLVM bitcode",
                "target_triple": triples[0], "callback_bindings": bindings}
    stage.require(data[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<HH", data, 16) == (1, 183),
                  "expected real ELF64 little-endian AArch64 relocatable: " + str(path))
    if callbacks:
        require_ci()
        names = subprocess.check_output(["llvm-nm", "--defined-only", str(path)], text=True)
        for name in callbacks:
            stage.require(name in names, "actual real-ON ELF callback absent: " + name)
    return {"sha256": stage.digest(data), "size": len(data), "machine": "AArch64", "type": "ET_REL"}


def disabled_consumer_rails(tree):
    dt = module("real_on_compiled_dt", "ci/check-native-modem-image-dt.py").hif
    stage.require(tree["/modem"].get("status") == b"disabled\0", "compiled CI DT activated CCCI consumer")
    owners = dt.phandle_owners(tree)
    rails = {}
    for supply, child in (("md-vmodem-supply", "vbuck2"), ("md-vsram-supply", "vsram-modem"),
                          ("md-vdigrf-supply", "vbuck1")):
        refs = dt.cells(tree["/modem"].get(supply, b""))
        stage.require(len(refs) == 1 and refs[0] in owners, "compiled CI supply is unresolved: " + supply)
        node = owners[refs[0]]
        stage.require(node.rsplit("/", 1)[1] == child and tree[node].get("status") == b"disabled\0",
                      "compiled CI rail was activated/replaced: " + supply)
        rails[supply] = node
    # Preserve whatever status the unchanged parent gives MD supplier/domain0.
    # Those first-OFF provider nodes are not the disabled CCCI consumer.
    return {"consumer": "/modem", "rails": rails}


def build(kernel, input_profile, config, output, report, enable_real_on=False):
    # This guard precedes subprocesses, mutation and even output allocation.
    require_ci()
    stage.require(enable_real_on is True, "compiling real ON requires explicit --enable-real-on")
    kernel, output, report = isolated(kernel), isolated(output), isolated(report)
    stage.require(kernel not in output.parents and output not in kernel.parents and
                  kernel not in report.parents and not output.exists() and not report.exists(),
                  "build outputs must be fresh and separate from source")
    result = {"status": "preparing", "scope": "actual native objects + disabled-consumer DT only; no link/boot"}
    report.parent.mkdir(parents=True, exist_ok=True)
    def save():
        report.write_text(json.dumps(result, indent=2) + "\n")
    save()
    try:
        result["source"] = prepare(kernel, input_profile, enable_real_on)
        result["variants"] = {}
        for enabled in (False, True):
            name = "real-on" if enabled else "default-off"
            variant = output / name
            log = report.parent / (report.stem + "-" + name + ".log")
            stage.require(not log.exists(), "CI compile log exists")
            result["phase"] = name + "-config"
            save()
            make = configure(kernel, variant, config, enabled, log)
            result["phase"] = name + "-objects"
            save()
            run([*make, *OBJECTS], log)
            callbacks = ("mt6878_md_real_boot_power_on", "mt6878_md_real_boot_attach") if enabled else ()
            result["variants"][name] = {"objects": {obj: object_identity(variant / obj,
                callbacks if obj == OBJECTS[0] else ()) for obj in OBJECTS},
                "config_sha256": stage.digest((variant / ".config").read_bytes())}
            result["phase"] = name + "-disabled-dtb"
            save()
            run([*make, "mediatek/" + Path(DTB).name], log)
            dt = module("real_on_read_compiled_dt", "ci/check-native-modem-image-dt.py").hif
            result["variants"][name]["disabled_consumers"] = disabled_consumer_rails(dt.read_tree(variant / DTB))
            result["variants"][name]["dtb_sha256"] = stage.digest((variant / DTB).read_bytes())
            save()
        stage.require(not list(output.rglob("*.ko")) and not list(output.rglob("vmlinux")),
                      "compile-only gate unexpectedly linked a module/kernel")
        result.update(status="passed", phase="complete")
        save()
        return result
    except Exception as error:
        result.update(status="failed", error=str(error))
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "prepare", "build", "emit-contract"))
    parser.add_argument("--prepared-kernel", type=Path)
    parser.add_argument("--pristine-kernel", type=Path)
    parser.add_argument("--input-profile", choices=("packaged", "r188"))
    parser.add_argument("--enable-real-on", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.command == "emit-contract":
        stage.require(args.pristine_kernel is not None, "emit-contract needs --pristine-kernel")
        print(json.dumps(source_contract(args.pristine_kernel), indent=2))
        return
    stage.require(args.prepared_kernel is not None and args.input_profile is not None,
                  "choose --prepared-kernel and explicit --input-profile")
    if args.command == "check":
        prefix, delta, profile = check(args.prepared_kernel, args.input_profile)
        result = {**profile, "status": "source-checked; not compiled",
                  "patches": [name for name, _ in prefix + delta]}
    elif args.command == "prepare":
        result = prepare(args.prepared_kernel, args.input_profile, args.enable_real_on)
    else:
        stage.require(all((args.config, args.output, args.report)), "build needs --config, --output and --report")
        result = build(args.prepared_kernel, args.input_profile, args.config, args.output,
                       args.report, args.enable_real_on)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
