#!/usr/bin/env python3
"""Preserve configured CI kernel exports; not a kernel SDK or runtime proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

FILES = (
    "Module.symvers", ".config", "System.map",
    "include/config/kernel.release", "include/generated/compile.h",
    "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dtb",
)


def collect(root, output, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected exact source commit")
    candidates = sorted({p.parent.resolve() for p in root.rglob("Module.symvers")
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
    output.mkdir(parents=True, exist_ok=False)
    for name in payloads:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kernel / name, target)
    manifest = {
        "source_commit": commit,
        "kernel_release": payloads["include/config/kernel.release"].decode().strip(),
        "scope": "configured kernel exports only; not module linkage or hardware support",
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
    args = parser.parse_args()
    print(json.dumps(collect(args.root, args.output, args.commit), indent=2))
