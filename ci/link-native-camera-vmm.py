#!/usr/bin/env python3
"""Compile and link the actual native CAM/ISP genpd graph in CI only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "patches/camera-camisp/native-integration"
SUPPLIER_SYMBOLS = ("mt6878_vmm_supplier_init", "mt6878_vmm_check",
                    "mt6878_vmm_isp_vcore_ctl_set")


def run(command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(md_on_adoption=False):
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
    report = ROOT / "out/kernel-object-smoke" / (
        "native-md-camera-vmm-link" if md_on_adoption else "native-camera-vmm-link")
    report.mkdir(exist_ok=False)
    result = dict(status="started", commit=os.environ["GITHUB_SHA"],
                  scope="real genpd provider vmlinux link; no installation, DT activation or hardware test",
                  patch_sha256=sha(DRAFT / "native-provider.patch"),
                  md_on_adoption=md_on_adoption, variants={})
    try:
        run(["python3", DRAFT / "check.py"])
        if md_on_adoption:
            md = ROOT / "patches/modem/md-pm-integration"
            md_plan = json.loads((md / "STAGING.json").read_text())
            for field in ("patch", "canonical_helper"):
                if sha(md / md_plan[field]["path"]) != md_plan[field]["sha256"]:
                    raise ValueError("reviewed MD staging input changed: " + field)
            archive = kernel.parent / ("linux-postmarketos-mediatek-mt6878-" + plan["kernel_commit"] + ".tar.gz")
            pristine = kernel.parent / "md-native-pristine"
            pristine.mkdir(exist_ok=False)
            members = ["drivers/pmdomain/mediatek/mtk-pm-domains.c",
                       "drivers/pmdomain/mediatek/mtk-pm-domains.h"]
            with tarfile.open(archive, "r:gz") as source:
                for name in members:
                    target = pristine / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    member = source.getmember("linux-" + plan["kernel_commit"] + "/" + name)
                    if not member.isfile():
                        raise ValueError("not a pristine provider source")
                    target.write_bytes(source.extractfile(member).read())
            run(["python3", md / "stage.py", "--kernel", pristine,
                 "--prepared-kernel", kernel, "--ci-apply"])
            run(["python3", DRAFT / "generate.py", "--md-on-adoption",
                 "--kernel-archive", archive, "--vendor-repo", ROOT / "out/infra-vendor",
                 "--modules-repo", ROOT / "out/camera-modules",
                 "--prepared-kernel", kernel, "--ci-apply"])
            result["md_patch_sha256"] = sha(md / md_plan["patch"]["path"])
            result["composite_report"] = json.loads((DRAFT / "md-on-adoption-report.json").read_text())
        else:
            patch = DRAFT / "native-provider.patch"
            run(["git", "-C", kernel, "apply", "--check", patch])
            run(["git", "-C", kernel, "apply", patch])
        # Isolated smoke dirs have no parent Kbuild entry. Reject an accidental
        # parent link instead of linking duplicate leaf/supplier definitions.
        makefile = (kernel / "drivers/pmdomain/mediatek/Makefile").read_text()
        if any(name in makefile for name in ("tetris-cam-power-smoke", "tetris-vmm-supplier-smoke")):
            raise ValueError("duplicate stand-alone VMM route entered real Kbuild")
        # Linux tracks configuration dependencies per object. Resolve and link
        # both variants while retaining the unchanged objects between them.
        output = Path("/tmp/tetris-kernel-smoke/native-camera-vmm-combined")
        output.mkdir(exist_ok=False)
        for unit in ("y", "n"):
            shutil.copyfile(ROOT / smoke.PACKAGE / smoke.CONFIG, output / ".config")
            config = [kernel / "scripts/config", "--file", output / ".config"]
            for symbol in plan["required_enabled"]:
                config.extend(["-e", symbol])
            if md_on_adoption:
                for symbol in ("OF_OVERLAY", "OF_UNITTEST", "OF_DYNAMIC", "MEMORY_HOTREMOVE"):
                    config.extend(["-d", symbol])
            config.extend(["-e" if unit == "y" else "-d", "KUNIT"])
            run(config)
            make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1",
                    "KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=", "KBUILD_MODPOST_SKIP="]
            run([*make, "olddefconfig"])
            text = (output / ".config").read_text().splitlines()
            expected_unit = "CONFIG_KUNIT=y" if unit == "y" else "# CONFIG_KUNIT is not set"
            if expected_unit not in text:
                raise ValueError("KUNIT variant did not resolve: " + unit)
            if any("CONFIG_" + symbol + "=y" not in text for symbol in plan["required_enabled"]):
                raise ValueError("native genpd build dependency missing")
            if md_on_adoption:
                for symbol, value in md_plan["ci"]["required_resolved_config"].items():
                    expected = "CONFIG_" + symbol + "=y" if value == "y" else "# CONFIG_" + symbol + " is not set"
                    if expected not in text:
                        raise ValueError("MD static diagnostic config unresolved: " + symbol)
            run([*make, "-k", *plan["combined_objects"]])
            supplier = output / "drivers/pmdomain/mediatek/native-vmm/mt6878-vmm-supplier.o"
            symbols = subprocess.check_output(["llvm-nm", "--defined-only", supplier], text=True)
            defined = {line.split()[-1] for line in symbols.splitlines() if line.split()}
            for name in SUPPLIER_SYMBOLS:
                if name not in defined:
                    raise ValueError("missing actual supplier object definition: " + name)
            run([*make, "vmlinux"])
            with (output / "vmlinux").open("rb") as binary:
                elf = binary.read(20)
            if elf[:6] != b"\x7fELF\x02\x01" or int.from_bytes(elf[18:20], "little") != 183:
                raise ValueError("not the genuine ARM64 vmlinux")
            variant = report / ("kunit-" + unit)
            variant.mkdir()
            shutil.copyfile(output / ".config", variant / "config")
            result["variants"][unit] = {
                "vmlinux_sha256": sha(output / "vmlinux"),
                "objects": {name: {**smoke.object_identity(output / name),
                                   "sha256": sha(output / name)} for name in plan["combined_objects"]},
                "supplier_symbols": list(SUPPLIER_SYMBOLS),
                "supplier_resolution": "real object definitions and strict vmlinux link; final ThinLTO may inline helpers"}
        result["status"] = "passed"
    except BaseException as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        (report / "BUILD-MANIFEST.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md-on-adoption", action="store_true")
    main(parser.parse_args().md_on_adoption)
