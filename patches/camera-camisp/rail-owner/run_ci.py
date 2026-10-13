#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""CI-only real regulator object build in a prepared pinned kernel; never boot."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import re
import subprocess

import check
import generate as gen


def ci_only():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("native camera rail compilation is CI-only")


def run(command):
    subprocess.run(list(map(str, command)), check=True)


def security_profile(text):
    profile = {}
    families = ("LTO", "CFI", "SHADOW_CALL_STACK", "STACKPROTECTOR", "ARM64_PTR_AUTH", "ARM64_BTI", "RANDOMIZE")
    for line in text.splitlines():
        match = re.fullmatch(r"CONFIG_(\w+)=(.+)|# CONFIG_(\w+) is not set", line)
        if not match:
            continue
        symbol, value = (match[1], match[2]) if match[1] else (match[3], "n")
        if any(symbol == family or symbol.startswith(family + "_") for family in families):
            profile[symbol] = value
    return profile


def verify_security_profile(original, resolved):
    expected, actual = security_profile(original), security_profile(resolved)
    if expected.get("LTO_CLANG_THIN") != "y" or expected.get("CFI") != "y":
        raise ValueError("shipping ThinLTO/CFI profile is missing")
    for symbol, value in expected.items():
        if actual.get(symbol, "n") != value:
            raise ValueError("shipping security profile changed: " + symbol)
    return expected


def verify_prepared_owner(kernel, base):
    # Kconfig/Makefile have packaged additions; actual GPIO/pinctrl code must not.
    table, _ = gen.prepared_pin_table(base)
    hashes = {}
    for path in gen.NATIVE:
        if path in (gen.KCONFIG, gen.MAKEFILE):
            continue
        data = (kernel / path).read_bytes()
        expected = table if path == gen.PIN_TABLE else base[path]
        if data != expected.encode():
            raise ValueError("prepared native owner/framework differs from pin: " + path)
        hashes[path] = gen.sha(data)
    return hashes


def main():
    ci_only()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-kernel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--kernel-archive", type=Path, required=True)
    args = parser.parse_args()
    for key in ("KBUILD_EXTRA_SYMBOLS", "KBUILD_KCONFIG", "KCONFIG_CONFIG", "MAKEFLAGS", "KCFLAGS", "KCPPFLAGS"):
        if os.environ.get(key):
            raise ValueError("inherited build override forbidden: " + key)
    base, payload, _ = check.check(archive=args.kernel_archive,
                                 device_repo=args.device_repo, modules_repo=args.modules_repo)
    kernel = args.prepared_kernel.resolve()
    output, report = args.output.resolve(), args.report.resolve()
    if kernel in (output, report) or output == report:
        raise ValueError("prepared kernel, isolated output and report must be separate")
    prepared_hashes = verify_prepared_owner(kernel, base)
    if (kernel / gen.DRIVER).exists():
        raise ValueError("rail provider is already staged; use a fresh prepared tree")
    patch = gen.HERE / "provider.patch"
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=kernel, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=kernel, check=True)
    for path in (gen.DRIVER, gen.BINDING):
        if (kernel / path).read_text() != payload[path]:
            raise ValueError("staged rail provider bytes changed: " + path)
    output.mkdir(parents=True, exist_ok=False)
    report.mkdir(parents=True, exist_ok=False)
    shipping = gen.PACKAGE / "config-postmarketos-mediatek-mt6878.aarch64"
    original = shipping.read_text()
    profile = verify_security_profile(original, original)
    shutil.copyfile(shipping, output / ".config")
    enabled = ("OF", "GPIOLIB", "PINCTRL_MT6878", "REGULATOR", "REGULATOR_TETRIS_CAMERA_GPIO")
    config = [kernel / "scripts/config", "--file", output / ".config"]
    for symbol in enabled:
        config.extend(["-e", symbol])
    make = ["make", "-C", kernel, f"O={output}", "ARCH=arm64", "LLVM=1", "-j4"]
    manifest = {"status": "started", "scope": "real ARM64 regulator object only; no DT, linking, installation or hardware",
                "kernel_commit": gen.KERNEL, "device_modules_commit": gen.DEVICE, "modules_commit": gen.MODULES,
                "source_sha256": gen.sha((kernel / gen.DRIVER).read_bytes()),
                "patch_sha256": gen.sha(patch.read_bytes()),
                "evidence_sha256": gen.sha((gen.HERE / "evidence.json").read_bytes()),
                "shipping_config_sha256": gen.sha(shipping.read_bytes()), "security_profile": profile,
                "prepared_owner_sha256": prepared_hashes}
    manifest_path = report / "BUILD-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    try:
        run(config)
        manifest["compiler"] = subprocess.check_output(["clang", "--version"], text=True).splitlines()[0]
        run([*make, "olddefconfig"])
        resolved_text = (output / ".config").read_text()
        verify_security_profile(original, resolved_text)
        resolved = resolved_text.splitlines()
        for symbol in enabled:
            if f"CONFIG_{symbol}=y" not in resolved:
                raise ValueError("unresolved rail owner dependency: " + symbol)
        shutil.copyfile(output / ".config", report / "isolated.config")
        target = gen.DRIVER.removesuffix(".c") + ".o"
        run([*make, target])
        artifact = output / target
        helper = gen.ROOT / "ci/kernel-object-smoke.py"
        spec = importlib.util.spec_from_file_location("rail_kernel_smoke", helper)
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        identity = smoke.object_identity(artifact)
        data = artifact.read_bytes()
        if list(output.rglob("*.ko")) or (output / "vmlinux").exists():
            raise ValueError("object-only rail gate produced a runtime module/kernel")
        shutil.copyfile(artifact, report / artifact.name)
        manifest.update(status="passed", object=target, object_sha256=hashlib.sha256(data).hexdigest(),
                        object_identity=identity, identity_helper_sha256=gen.sha(helper.read_bytes()),
                        config_sha256=gen.sha((output / ".config").read_bytes()))
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
