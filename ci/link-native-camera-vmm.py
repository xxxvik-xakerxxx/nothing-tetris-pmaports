#!/usr/bin/env python3
"""Compile and link the actual native CAM/ISP genpd graph in CI only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "patches/camera-camisp/native-integration"


def run(command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("native CAM/ISP build/link is GitHub CI-only")
    for key in ("KBUILD_MODPOST_WARN", "KBUILD_MODPOST_NOFINAL", "KBUILD_MODPOST_SKIP",
                "KBUILD_EXTRA_SYMBOLS", "KBUILD_KCONFIG", "KCONFIG_CONFIG", "MAKEFLAGS"):
        if os.environ.get(key):
            raise ValueError("inherited build override forbidden: " + key)
    spec = importlib.util.spec_from_file_location("camera_real_smoke", ROOT / "ci/kernel-object-smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    plan = json.loads((DRAFT / "STAGING.json").read_text())
    if plan["kernel_commit"] != "d84b264a54a37611f2f46bc19363cb9b41606205" or \
            plan["default_selector"] != "CONFIG_MTK_MT6878_NATIVE_VMM=n":
        raise ValueError("native camera integration selection/pin drift")
    kernel = Path("/tmp/tetris-kernel-smoke") / ("linux-" + plan["kernel_commit"])
    report = ROOT / "out/kernel-object-smoke/native-camera-vmm-link"
    report.mkdir(exist_ok=False)
    result = dict(status="started", commit=os.environ["GITHUB_SHA"],
                  scope="real genpd provider vmlinux link; no installation, DT activation or hardware test",
                  patch_sha256=sha(DRAFT / "native-provider.patch"), variants={})
    try:
        run(["python3", DRAFT / "check.py"])
        patch = DRAFT / "native-provider.patch"
        run(["git", "-C", kernel, "apply", "--check", patch])
        run(["git", "-C", kernel, "apply", patch])
        # Isolated smoke dirs have no parent Kbuild entry. Reject an accidental
        # parent link instead of linking duplicate leaf/supplier definitions.
        makefile = (kernel / "drivers/pmdomain/mediatek/Makefile").read_text()
        if any(name in makefile for name in ("tetris-cam-power-smoke", "tetris-vmm-supplier-smoke")):
            raise ValueError("duplicate stand-alone VMM route entered real Kbuild")
        for unit in ("y", "n"):
            output = Path("/tmp/tetris-kernel-smoke") / ("native-camera-vmm-" + unit)
            output.mkdir(exist_ok=False)
            shutil.copyfile(ROOT / smoke.PACKAGE / smoke.CONFIG, output / ".config")
            config = [kernel / "scripts/config", "--file", output / ".config"]
            for symbol in plan["required_enabled"]:
                config.extend(["-e", symbol])
            config.extend(["-e" if unit == "y" else "-d", "KUNIT"])
            run(config)
            make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1",
                    "KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=", "KBUILD_MODPOST_SKIP="]
            run([*make, "olddefconfig"])
            text = (output / ".config").read_text().splitlines()
            if any("CONFIG_" + symbol + "=y" not in text for symbol in plan["required_enabled"]):
                raise ValueError("native genpd build dependency missing")
            run([*make, "-k", *plan["combined_objects"]])
            run([*make, "vmlinux"])
            with (output / "vmlinux").open("rb") as binary:
                elf = binary.read(20)
            if elf[:6] != b"\x7fELF\x02\x01" or int.from_bytes(elf[18:20], "little") != 183:
                raise ValueError("not the genuine ARM64 vmlinux")
            symbols = subprocess.check_output(["llvm-nm", "--defined-only", output / "vmlinux"], text=True)
            for name in ("mt6878_vmm_supplier_init", "mt6878_vmm_check", "mt6878_vmm_isp_ctl_set"):
                if not any(line.split()[-1] == name for line in symbols.splitlines() if line.split()):
                    raise ValueError("missing combined native supplier symbol: " + name)
            variant = report / ("kunit-" + unit)
            variant.mkdir()
            shutil.copyfile(output / ".config", variant / "config")
            result["variants"][unit] = {
                "vmlinux_sha256": sha(output / "vmlinux"),
                "objects": {name: {**smoke.object_identity(output / name),
                                   "sha256": sha(output / name)} for name in plan["combined_objects"]},
                "supplier_symbols": "resolved in actual vmlinux"}
        result["status"] = "passed"
    except BaseException as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        (report / "BUILD-MANIFEST.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
