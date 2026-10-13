#!/usr/bin/env python3
"""Compile the concrete handoff + actual CCCI caller units in Linux GitHub CI only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import stage

OBJECTS = ("fsm/ccci_tetris_native_start.o", "fsm/modem_sys1.o", "fsm/ccci_fsm.o",
           "fsm/md_sys1_platform.o", "hif/ccci_hif.o", "hif/ccci_hif_ccif.o", "hif/ccci_dpmaif_com.o")
REQUIRED = {"fsm/ccci_tetris_native_start.o": ("ccci_tetris_owner_start", "ccci_tetris_native_first_start", "ccci_tetris_native_probe"),
            "fsm/ccci_fsm.o": ("ccci_tetris_native_queue_start",),
            "hif/ccci_hif.o": ("ccci_tetris_hif_register", "ccci_tetris_hif_claim", "ccci_tetris_hif_start")}
NATIVE_CONFIG = "MTK_MT6878_MODEM_NATIVE_START_STAGING"


def real_ci():
    # The frozen helper's plain import must refer to its own staging module,
    # not this directory's identically named stage.py.
    previous = sys.modules.get("stage")
    sys.modules["stage"] = stage.load("native_start_real_ci_stage", stage.HERE.parent / "real-boot/stage.py")
    try:
        return stage.load("native_start_ci_base", stage.HERE.parent / "real-boot/ci.py")
    finally:
        if previous is None:
            del sys.modules["stage"]
        else:
            sys.modules["stage"] = previous


def build(kernel, pristine, config, vendor, output, report, enable=False):
    real = real_ci()
    real.require_ci()
    stage.require(enable, "native first-start compile requires explicit --enable-native-start")
    stage.verify_manifest()
    kernel, output, report = map(real.isolated, (kernel, output, report))
    stage.require(not output.exists() and not report.exists() and kernel not in output.parents and
                  kernel not in report.parents and output not in kernel.parents,
                  "fresh CI outputs must be separate from kernel")
    pristine_hashes = stage.pristine_inputs(pristine)
    bundles = stage.build(vendor, pristine)
    patch, before, _ = bundles["native-on-api.patch"]
    for name, text in before.items():
        path = kernel / name
        stage.require(path.resolve() == path and path.is_file() and path.stat().st_nlink == 1 and
                      path.read_text() == text, "prepared real-ON source differs/hardlinked: " + name)
    stage.require((stage.HERE / "native-on-api.patch").read_text() == patch,
                  "native-on API patch is stale")
    result = {"status": "preparing", "scope": "native supplier + seven actual CCCI translation units; no link/runtime",
              "shipping_activation": "none; no DT enablement or installation",
              "pristine_linux": stage.LINUX, "pristine_inputs_sha256": pristine_hashes}
    report.parent.mkdir(parents=True, exist_ok=True)
    def save():
        report.write_text(json.dumps(result, indent=2) + "\n")
    save()
    try:
        real.apply_source(kernel, patch.encode(), strict=True, check_only=True)
        real.apply_source(kernel, patch.encode(), strict=True)
        result["patches_sha256"] = {name: hashlib.sha256(data.encode()).hexdigest()
                                    for name, (data, _, _) in bundles.items()}
        result["variants"] = {}
        for enabled in (False, True):
            name = "native-start" if enabled else "default-off"
            variant = output / name
            log = report.parent / (report.stem + "-" + name + ".log")
            stage.require(not log.exists(), "CI log already exists")
            make = real.configure(kernel, variant, config, True, log)
            real.run([kernel / "scripts/config", "--file", variant / ".config",
                      "--enable" if enabled else "--disable", NATIVE_CONFIG], log)
            real.run([*make, "olddefconfig"], log)
            resolved = (variant / ".config").read_text().splitlines()
            wanted = "CONFIG_" + NATIVE_CONFIG + "=y" if enabled else "# CONFIG_" + NATIVE_CONFIG + " is not set"
            stage.require(wanted in resolved, "native API configuration did not resolve")
            real.run([*make, "drivers/pmdomain/mediatek/mtk-pm-domains.o"], log)
            callbacks = ("mt6878_md_native_on_validate", "mt6878_md_native_on_latch") if enabled else ()
            objects = {"native_supplier": real.object_identity(
                variant / "drivers/pmdomain/mediatek/mtk-pm-domains.o", callbacks)}
            real.run([*make, "mediatek/" + Path(real.DTB).name], log)
            dt = real.module("native_start_dtb", "ci/check-native-modem-image-dt.py").hif
            disabled = real.disabled_consumer_rails(dt.read_tree(variant / real.DTB))
            if enabled:
                closure = stage.load("native_start_compile_closure", stage.REPO / "patches/modem/drafts/runtime-link-closure/link_full.py")
                disposable = output / "vendor"
                manifest, _ = closure.stage(vendor, disposable, {})
                vpatch, vbefore, vafter = bundles["ccci-native-start.patch.vendor"]
                stage.require(vpatch == (stage.HERE / "ccci-native-start.patch.vendor").read_text(), "CCCI patch stale")
                for path, text in vbefore.items():
                    stage.require((disposable / path).read_text() == text, "complete CCCI compile base differs: " + path)
                real.apply_source(disposable, vpatch.encode(), strict=True, check_only=True)
                real.apply_source(disposable, vpatch.encode(), strict=True)
                real.run([*make, "modules_prepare"], log)
                flags = manifest["vendor_kcflags"] + " -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1"
                flags += " -DCONFIG_MTK_ECCCI_TETRIS_NATIVE_START=1 -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1"
                flags += " -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion"
                directory = disposable / stage.E
                command = [*make, "M=" + str(directory), "KERNEL_SRC=" + str(kernel),
                           "KERNEL_OUT=" + str(variant), "DEVICE_MODULES_PATH=" + str(disposable), "KCFLAGS=" + flags]
                command += [key + "=" + value for key, value in manifest["external_kbuild"].items()]
                command += ["CONFIG_MTK_ECCCI_TETRIS_OWNER=y", "CONFIG_MTK_ECCCI_TETRIS_NATIVE_START=y"]
                real.run([*command, *OBJECTS], log)
                for obj in OBJECTS:
                    target = directory / obj
                    objects[obj] = real.object_identity(target)
                    symbols = subprocess.check_output(["llvm-nm", "--defined-only", str(target)], text=True)
                    for symbol in REQUIRED.get(obj, ()):
                        stage.require(re.search(r"\b" + re.escape(symbol) + r"$", symbols, re.M),
                                      "actual native caller/definition missing: " + symbol)
                result["vendor_kcflags"] = flags
                result["compiled_vendor_sources"] = {path: hashlib.sha256((disposable / path).read_bytes()).hexdigest()
                                                     for path in vafter}
            result["variants"][name] = {"objects": objects, "disabled_consumers": disabled,
                "config_sha256": hashlib.sha256((variant / ".config").read_bytes()).hexdigest()}
            save()
        stage.require(not list(output.rglob("*.ko")) and not list(output.rglob("vmlinux")), "object gate linked runtime artifact")
        result["status"] = "passed"
        save()
    except Exception as error:
        result.update(status="failed", error=str(error))
        save()
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-kernel", type=Path, required=True)
    parser.add_argument("--pristine-kernel", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--enable-native-start", action="store_true")
    args = parser.parse_args()
    build(args.prepared_kernel, args.pristine_kernel, args.config, args.vendor,
          args.output, args.report, args.enable_native_start)


if __name__ == "__main__":
    main()
