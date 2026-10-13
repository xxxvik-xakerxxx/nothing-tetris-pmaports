#!/usr/bin/env python3
"""Compile the staged built-in stream lifecycle in GitHub CI, never install it."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DRIVER = "drivers/media/i2c/imx882-tetris-stream.c"
OBJECT = DRIVER.removesuffix(".c") + ".o"


def require_ci():
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("camera stream compilation/staging is GitHub CI-only")


def security_profile(text):
    families = ("LTO", "CFI", "SHADOW_CALL_STACK", "STACKPROTECTOR", "ARM64_PTR_AUTH", "ARM64_BTI", "RANDOMIZE")
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"CONFIG_(\w+)=(.+)|# CONFIG_(\w+) is not set", line)
        if match:
            key, value = (match[1], match[2]) if match[1] else (match[3], "n")
            if any(key == family or key.startswith(family + "_") for family in families):
                result[key] = value
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(args):
    require_ci()
    kernel, prepared, output, report = [value.resolve() for value in
        (args.prepared_kernel, args.prepared_output, args.output, args.report)]
    for left in (output, report):
        for right in (kernel, prepared):
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("camera output/report overlaps an input")
    if output == report or output in report.parents or report in output.parents:
        raise ValueError("camera output and report overlap")
    if output.exists() or report.exists():
        raise ValueError("camera outputs must be fresh")
    for key in ("KBUILD_EXTRA_SYMBOLS", "KBUILD_KCONFIG", "KCONFIG_CONFIG", "MAKEFLAGS", "KCFLAGS", "KCPPFLAGS"):
        if os.environ.get(key):
            raise ValueError("inherited build override forbidden: " + key)
    for path in prepared.rglob("*"):
        if path.is_symlink() and not (path == prepared / "source" and path.resolve() == kernel):
            raise ValueError("unexpected prepared-output symlink: " + str(path))
    original = (prepared / ".config").read_text()
    expected = security_profile(original)
    if expected.get("LTO_CLANG_THIN") != "y" or expected.get("CFI") != "y":
        raise ValueError("prepared ThinLTO/CFI profile missing")
    report.mkdir(parents=True)
    manifest = {"status": "started", "scope": "built-in ARM64 object only; no full link, DT activation, installation or capture",
                "pmaports": os.environ.get("GITHUB_SHA"), "input_config_sha256": sha(prepared / ".config"),
                "security_profile": expected}
    try:
        subprocess.run([sys.executable, "-B", str(ROOT / "patches/camera-camisp/stream-owner/stage.py"),
            "--prepared-kernel", str(kernel), "--kernel-archive", str(args.kernel_archive),
            "--device-repo", str(args.device_repo), "--modules-repo", str(args.modules_repo),
            "--ci-apply", "--report", str(report / "stage")], check=True)
        stage = json.loads((report / "stage/STAGE-MANIFEST.json").read_text())
        manifest["staging"] = stage
        shutil.copytree(prepared, output, symlinks=True)
        subprocess.run([str(kernel / "scripts/config"), "--file", str(output / ".config"),
                        "--enable", "VIDEO_IMX882_TETRIS"], check=True)
        make = ["make", "-C", str(kernel), "O=" + str(output), "ARCH=arm64", "LLVM=1", "-j4"]
        subprocess.run([*make, "olddefconfig"], check=True)
        resolved = (output / ".config").read_text()
        actual = security_profile(resolved)
        if any(actual.get(key, "n") != value for key, value in expected.items()):
            raise ValueError("camera stream changed inherited security profile")
        if "CONFIG_VIDEO_IMX882_TETRIS=y" not in resolved.splitlines():
            raise ValueError("built-in stream selector did not resolve")
        if sha(kernel / DRIVER) != stage["staged_sha256"][DRIVER]:
            raise ValueError("stream driver changed after staging")
        manifest["compiler"] = subprocess.check_output(["clang", "--version"], text=True).strip()
        if not re.search(r"clang version 21\.", manifest["compiler"]):
            raise ValueError("package-matching clang21 required")
        manifest["kernel_command"] = [*make, "KCFLAGS=-Werror", OBJECT]
        subprocess.run(manifest["kernel_command"], check=True)
        spec = importlib.util.spec_from_file_location("camera_stream_object_identity", ROOT / "ci/kernel-object-smoke.py")
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        manifest["object"] = {**smoke.object_identity(output / OBJECT), "sha256": sha(output / OBJECT)}
        manifest["resolved_config_sha256"] = sha(output / ".config")
        shutil.copyfile(output / OBJECT, report / Path(OBJECT).name)
        shutil.copyfile(output / ".config", report / "config")
        if sha(prepared / ".config") != manifest["input_config_sha256"]:
            raise ValueError("shared prepared configuration changed")
        manifest["status"] = "passed"
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        (report / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    require_ci()
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("prepared-kernel", "prepared-output", "kernel-archive", "device-repo", "modules-repo", "output", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
