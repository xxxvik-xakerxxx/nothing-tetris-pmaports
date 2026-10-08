#!/usr/bin/env python3
"""Preserve configured CI kernel exports; not a kernel SDK or runtime proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re

FILES = (
    "Module.symvers", ".config", "System.map",
    "include/config/kernel.release", "include/generated/compile.h",
    "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dtb",
)
MODEM_FILES = (
    "Module.symvers", "modules.order", "ccci_util/ccci_util_lib.ko",
    "eccci/ccci_md_all.ko", "eccci/ccci_auxadc.ko",
    "eccci/hif/ccci_ccif.ko", "eccci/hif/ccci_dpmaif.ko",
    "eccci/hif/ccci_cldma.ko", "eccci/fsm/ccci_fsm_scp.ko",
    "ccmni/ccmni.ko", "rps/rps_perf.ko",
)


def collect(root, output, commit, modem=False):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected exact source commit")
    # pmbootstrap keeps abuild output here. Never recurse through mounted
    # proc/sys/dev or /mnt/pmbootstrap inside a chroot.
    candidates = sorted({p.parent.resolve() for p in
                         root.glob("chroot_*/home/pmos/build/src/*/Module.symvers")
                         if (p.parent / "include/config/kernel.release").is_file()})
    if len(candidates) != 1:
        raise ValueError(f"expected one configured kernel, found {len(candidates)}")
    kernel = candidates[0]
    payloads = {}
    for name in FILES:
        path = kernel / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing, empty or symlinked kernel evidence: {name}")
        payloads[name] = path.read_bytes()
    config = payloads[".config"].decode()
    if "CONFIG_ARM64=y" not in config.splitlines():
        raise ValueError("not an ARM64 kernel configuration")
    for line in payloads["Module.symvers"].decode().splitlines():
        fields = line.split()
        if (len(fields) not in (4, 5) or
                not re.fullmatch(r"0x[0-9a-fA-F]{8}", fields[0]) or
                not fields[3].startswith("EXPORT_SYMBOL")):
            raise ValueError("malformed kernel export record")
    if modem:
        linkdir = kernel.parent / "tetris-modem-link"
        for name in MODEM_FILES:
            path = (linkdir / name).resolve(strict=True)
            if not path.is_relative_to(kernel.parent) or not path.is_file():
                raise ValueError(f"invalid modem build output: {name}")
            data = path.read_bytes()
            if not data:
                raise ValueError(f"empty modem build output: {name}")
            if name.endswith(".ko") and (len(data) < 20 or
                    data[:6] != b"\x7fELF\x02\x01" or
                    int.from_bytes(data[18:20], "little") != 183):
                raise ValueError(f"not an ELF64 little-endian AArch64 module: {name}")
            payloads["modem-link/" + name] = data
    output.mkdir(parents=True, exist_ok=False)
    for name in payloads:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payloads[name])
    manifest = {
        "source_commit": commit,
        "kernel_release": payloads["include/config/kernel.release"].decode().strip(),
        "scope": ("configured kernel and linked modem modules; NOT runtime validated or installed"
                  if modem else
                  "configured kernel exports only; not module linkage or hardware support"),
        "sha256": {name: hashlib.sha256(data).hexdigest()
                   for name, data in payloads.items()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--modem", action="store_true",
                        help="Require all nine linked ARM64 modem modules")
    args = parser.parse_args()
    print(json.dumps(collect(args.root, args.output, args.commit, args.modem), indent=2))
