#!/usr/bin/env python3
"""Read actual matched package modules/exports. No target code is executed."""
import argparse
import json
from pathlib import Path

import native_image_abi as abi

MODULES = ("eccci/ccci_md_all", "eccci/ccci_auxadc", "eccci/hif/ccci_ccif",
           "eccci/hif/ccci_dpmaif", "eccci/hif/ccci_cldma", "eccci/fsm/ccci_fsm_scp",
           "ccmni/ccmni", "rps/rps_perf")
API = ("mt6878_md_native_on_validate", "mt6878_md_native_on_latch")
MAP = "mtk_ccci_owned_mapped_copy"
OLD = {"mt6878_ccci_start_alloc", "mt6878_ccci_first_start", "mt6878_ccci_start_result"}


def check(kernel, vendor, modules, shipping_config, extra_tables):
    kernel, vendor, modules = map(Path, (kernel, vendor, modules))
    cfg = abi.config((kernel / ".config").read_text())
    security = abi.security_profile(abi.config(Path(shipping_config).read_text()), cfg)
    for symbol in ("MTK_MT6878_MODEM_REAL_BOOT_STAGING", "MTK_MT6878_MODEM_NATIVE_START_STAGING"):
        abi.require(cfg.get(symbol) == "y", "native kernel API disabled: " + symbol)
    for symbol in ("OF_DYNAMIC", "OF_OVERLAY", "OF_UNITTEST", "KEXEC", "KEXEC_FILE", "KEXEC_CORE"):
        abi.require(cfg.get(symbol, "n") == "n", "unsafe native kernel selector: " + symbol)
    tables = {"kernel": kernel / "Module.symvers", "util": vendor / "drivers/misc/mediatek/ccci_util/Module.symvers",
              "native": modules / "Module.symvers"}
    tables.update({"shipping-dependency-" + str(i): Path(path) for i, path in enumerate(extra_tables)})
    exports = abi.export_index({name: abi.symvers(path.read_text()) for name, path in tables.items()})
    paths = {name: modules / (name + ".ko") for name in MODULES}
    paths["provider/ccci_util_lib"] = tables["util"].parent / "ccci_util_lib.ko"
    images = {name: abi.elf(path, cfg) for name, path in paths.items()}
    vmlinux = abi.elf(kernel / "vmlinux", module=False)
    release = (kernel / "include/config/kernel.release").read_text().strip()
    core = images["eccci/ccci_md_all"]
    abi.require(set((*API, MAP)) <= core["imports"].keys(), "actual native consumer/provider calls lost")
    parts = (modules / "eccci/ccci_md_all.mod").read_text().split()
    abi.require(any(part.endswith("/fsm/ccci_tetris_native_start.o") for part in parts), "native START object omitted")
    abi.require(not any(part.endswith(("/fsm/ccci_tetris_owner.o", "/hif/ccci_tetris_hif_owned.o"))
                        for part in parts), "virtual OFF composition present")
    for name in (*API,):
        abi.require(name in exports and exports[name]["owner"] == "vmlinux" and
                    exports[name]["export"] == "EXPORT_SYMBOL_GPL", "native vmlinux API not actually exported")
    owners = {"vmlinux": vmlinux}
    for name, image in images.items():
        owner = image["metadata"]["name"][0]
        abi.require(owner == Path(name).name.replace("-", "_") and owner not in owners, "wrong/duplicate module identity")
        abi.require(image["metadata"]["vermagic"][0].startswith(release + " "), "module/kernel release mismatch")
        abi.require(image["metadata"]["vermagic"] == images["provider/ccci_util_lib"]["metadata"]["vermagic"],
                    "module ABI mismatch")
        abi.require(not (OLD & image["imports"].keys()), "legacy OFF dependency retained")
        owners[owner] = image
    report = {"status": "passed", "scope": "actual package-native module link/export closure only",
              "hardware": "untested", "activation": "consumer/HIF/rails disabled; no autoload/START",
              "security_profile": security, "config_sha256": abi.sha(kernel / ".config"),
              "vmlinux_sha256": vmlinux["sha256"], "modules": {}, "dependencies": {},
              "symvers_sha256": {name: abi.sha(path) for name, path in tables.items()}}
    for name, image in images.items():
        result = abi.closure(image, exports, cfg)
        for symbol, row in result["imports"].items():
            owner = abi.owner_name(row["owner"])
            if owner not in owners:
                value = Path(row["owner"] + ".ko")
                abi.require(".." not in value.parts, "export owner path traversal")
                path = value if value.is_absolute() else kernel / value
                abi.require(path.resolve() == path and any(root.resolve() in path.parents
                    for root in (kernel, vendor.parent)), "dependency escapes actual package output")
                owners[owner] = abi.elf(path, cfg)
                abi.require(owners[owner]["metadata"]["name"] == [owner], "wrong dependency ELF owner")
                abi.require(owners[owner]["metadata"]["vermagic"] == image["metadata"]["vermagic"],
                            "dependency ABI mismatch")
                report["dependencies"][owner] = {"sha256": owners[owner]["sha256"], "path": str(path)}
            abi.require(symbol in owners[owner]["definitions"] and
                        "__ksymtab_" + symbol in owners[owner]["definitions"], "export has no actual provider: " + symbol)
        report["modules"][name] = {**result, "sha256": image["sha256"]}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kernel", "vendor", "modules", "shipping-config", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--extra-table", action="append", type=Path, default=[])
    args = parser.parse_args()
    target = args.report
    if target.exists():
        raise ValueError("fresh module report required")
    try:
        result = check(args.kernel, args.vendor, args.modules, args.shipping_config, args.extra_table)
    except Exception as error:
        target.write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise
    target.write_text(json.dumps(result, indent=2) + "\n")
