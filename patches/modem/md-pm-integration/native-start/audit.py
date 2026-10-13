#!/usr/bin/env python3
"""Read pinned source contracts only. Never import/execute the ATF fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

import stage

ATF = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
CONTRACT = "634789437e3f80a0129f00e5cff922bd8cdbb64b"


def object_text(root, pin, path):
    return subprocess.check_output(["git", "-C", str(root), "show", pin + ":" + path], text=True)


def evidence():
    root = stage.UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878"
    sources = {}
    for path in (stage.E + "fsm/modem_sys1.c", stage.E + "fsm/md_sys1_platform.c",
                 stage.E + "inc/modem_secure_base.h", stage.E + "hif/ccci_hif.c",
                 stage.E + "hif/ccci_hif_ccif.c", stage.E + "hif/ccci_dpmaif_com.c"):
        text = object_text(root, stage.VENDOR, path)
        sources[path] = {"revision": stage.VENDOR, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    md = object_text(root, stage.VENDOR, stage.E + "fsm/modem_sys1.c")
    platform = object_text(root, stage.VENDOR, stage.E + "fsm/md_sys1_platform.c")
    for source, needles in ((md, ("start_platform(md)", "power_on(md)", "let_md_go(md)",
                                  "request_irq(md->md_wdt_irq_id, md_cd_wdt_isr")),
                            (platform, ("static int md_start_platform(", "md_cd_power_off(md, 0);",
                                        "MD_POWER_CONFIG,\n\t\tMD_KERNEL_BOOT_UP, 0, 0, 0, 0, 0, &res"))):
        for needle in needles:
            stage.require(needle in source, "missing exact B4.1 start contract: " + needle)
    power = object_text(stage.REPO, CONTRACT, "patches/modem/test-atf-power-contract.py")
    stage.require('SHA = "' + ATF + '"' in power and
                  'BOOT = 0x21b20300' in power and
                  'assert (ret, out) == (0, (0x12345678, 0xabcdef01, 1))' in power,
                  "POWER/0 defined return contract differs")
    sources["tracked-atf-power"] = {"revision": CONTRACT,
        "path": "patches/modem/test-atf-power-contract.py", "sha256": hashlib.sha256(power.encode()).hexdigest(),
        "method": "source read only; not imported or executed"}
    # Verify the companion object exists; do not adopt its checkout/untracked files.
    companion = stage.UPSTREAM / "android_kernel_modules_nothing_mt6878"
    tree = subprocess.check_output(["git", "-C", str(companion), "rev-parse", stage.MODULES + "^{tree}"], text=True).strip()
    linux = stage.UPSTREAM / ("linux-" + stage.LINUX)
    base = stage.load("native_start_linux_pin", stage.HERE.parent / "real-boot/audit.py")
    archive = stage.UPSTREAM / ("linux-" + stage.LINUX + ".tar.gz")
    digest = hashlib.sha512()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    stage.require(digest.hexdigest() == base.LINUX_ARCHIVE_SHA512, "not checksum-pinned Linux archive")
    selected = {"kernel/reboot.c", "kernel/power/main.c", "include/linux/pm_runtime.h"}
    archive_files = {}
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            path = member.name.partition("/")[2]
            if path in selected:
                stage.require(member.isfile() and path not in archive_files, "ambiguous Linux archive path")
                archive_files[path] = source.extractfile(member).read()
    stage.require(archive_files.keys() == selected, "missing Linux export sources")
    for path in ("kernel/reboot.c", "kernel/power/main.c", "include/linux/pm_runtime.h"):
        stage.require((linux / path).read_bytes() == archive_files[path], "Linux source differs from d84: " + path)
        text = (linux / path).read_text()
        sources["linux:" + path] = {"revision": stage.LINUX, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        if path == "kernel/reboot.c":
            stage.require("DEFINE_MUTEX(system_transition_mutex);" in text and
                          "EXPORT_SYMBOL_GPL(system_transition_mutex)" not in text,
                          "system mutex export contract changed")
        if path == "kernel/power/main.c":
            stage.require("EXPORT_SYMBOL_GPL(lock_system_sleep);" in text and
                          "EXPORT_SYMBOL_GPL(unlock_system_sleep);" in text, "missing real sleep lock exports")
    frozen = json.loads((stage.HERE.parent / "real-boot/SOURCE-EVIDENCE.json").read_text())
    stage.require(frozen["pins"]["linux"] == stage.LINUX and frozen["pins"]["vendor"] == stage.VENDOR,
                  "native supplier source pins differ")
    return {"pins": {"vendor": stage.VENDOR, "modules": stage.MODULES, "modules_tree": tree,
                     "linux": stage.LINUX, "atf_payload_sha256": ATF}, "sources": sources,
            "power0": {"x0": "0xc2000505", "x1": 6, "x2": 0, "x3_x7": 0,
                       "a0": "status; nonzero -> EIO, raw retained",
                       "a1_a2": "defined boot-status register words; diagnostic, not readiness flags",
                       "a3": "boot-slave register readback, require 1", "boot_register": "0x21b20300",
                       "outer_admission": "separate; not manufactured from return status"},
            "kernel_export_boundary": "system_transition_mutex not exported; module uses exported lock_system_sleep/unlock_system_sleep",
            "validation": "source checks only; no ATF fixture execution or hardware permission claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    value = evidence()
    if args.emit:
        print(json.dumps(value, indent=2))
    else:
        stage.require(value == json.loads((stage.HERE / "SOURCE-EVIDENCE.json").read_text()), "native-start evidence drift")
        print("Exact B4.1 callers, POWER/0 source contract and kernel export boundary: PASS")


if __name__ == "__main__":
    main()
