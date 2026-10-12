#!/usr/bin/env python3
"""Link the native CCF candidate against the genuine r181/r182 ABI, CI only."""
import importlib.util
import json
import os
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("native clock compilation/linkage is GitHub CI-only")
    for key in ("KBUILD_MODPOST_WARN", "KBUILD_MODPOST_NOFINAL", "KBUILD_MODPOST_SKIP",
                "KBUILD_EXTRA_SYMBOLS", "KBUILD_KCONFIG", "KCONFIG_CONFIG", "MAKEFLAGS"):
        if os.environ.get(key):
            raise ValueError("inherited build override forbidden: " + key)
    link = load("infra_real_link", HERE.parent / "drafts/runtime-link-closure/link_full.py")
    smoke = load("infra_object_identity", ROOT / "ci/kernel-object-smoke.py")
    parent = Path("/tmp/tetris-kernel-smoke/r181-module")
    kernel = parent / ("linux-" + link.LINUX)
    configured = parent / "kernel-output"
    if link.sha(configured / ".config") != link.CONFIG_SHA or \
            link.sha(configured / "Module.symvers") != link.EXPORTS_SHA:
        raise ValueError("requires unchanged genuine r181/r182 config and exports")
    packaged = json.loads((ROOT / "out/kernel-object-smoke/packaged-smem.json").read_text())
    if packaged.get("status") != "passed":
        raise ValueError("requires the completed actual ABI preparation")
    destination = ROOT / "out/kernel-object-smoke/infra-clock-link"
    destination.mkdir(exist_ok=False)
    report = dict(status="started", linux_commit=link.LINUX,
                  commit=os.environ["GITHUB_SHA"], config_sha256=link.CONFIG_SHA,
                  kernel_symvers_sha256=link.EXPORTS_SHA,
                  scope="strict module link only; no load, DT change or hardware access")
    try:
        source = HERE / "clk-mt6878-infra-ao.c"
        shutil.copyfile(source, destination / source.name)
        report["source_sha256"] = link.sha(source)
        (destination / "Kbuild").write_text(
            "obj-m += clk-mt6878-infra-ao.o\n"
            "ccflags-y += -I$(srctree)/drivers/clk/mediatek\n")
        link.logged_build(["make", "-j2", "-C", kernel, "O=" + str(configured),
                           "ARCH=arm64", "LLVM=1", "M=" + str(destination),
                           "KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=",
                           "KBUILD_MODPOST_SKIP=", "KBUILD_EXTRA_SYMBOLS=",
                           "KCFLAGS=-Werror", "modules"], destination / "link.log", report)
        module = destination / "clk-mt6878-infra-ao.ko"
        report["module"] = link.module_identity(module, smoke,
                                               packaged["private_smem_binding"]["vermagic"])
        if report["module"]["depends"]:
            raise ValueError("unexpected external module dependency")
        exports = link.symvers(configured / "Module.symvers")
        required = link.native_symbols(module, "--undefined-only")
        if not required or not required <= exports.keys():
            raise ValueError("native CCF import absent from genuine kernel exports")
        report["imports"] = {symbol: exports[symbol] for symbol in sorted(required)}
        if link.sha(configured / ".config") != link.CONFIG_SHA or \
                link.sha(configured / "Module.symvers") != link.EXPORTS_SHA:
            raise ValueError("genuine kernel ABI changed during clock linkage")
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        (destination / "BUILD-MANIFEST.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: native infra clock module, genuine r181/r182 exports, no hardware activation")


if __name__ == "__main__":
    main()
