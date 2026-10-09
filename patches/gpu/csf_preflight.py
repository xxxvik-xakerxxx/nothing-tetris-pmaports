#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Bounded offline Panthor CSF format preflight, never a hardware boot proof."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_BYTES = 4 * 1024 * 1024
B41_SHA = "81bef7649fc3c056fae347c4511dd9d2f80f081dc07ac6c4ad9c8fbb7c302f56"
SHARED_VA = 0x04000000
SUPPORTED_FLAGS = 0xc000003f
SOURCE_PINS = {
    "panthor_fw.c": "d1ebd4c342bb7c3714c51273239f1d8037cbb206df6ed1cd9e7e5796b3633b0d",
    "panthor_devfreq.c": "f769cac08256088ef0b144ae857bebaf5494b6c0830d7c298f894c65ce4e3eab",
    "panthor_device.c": "af4ed5a9092da8779d76be2d68096c8dea22c1f5091a8145965eaba9d833b4fd",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def firmware_path(gpu_id):
    require(0 <= gpu_id <= 0xffffffff, "invalid GPU_ID")
    # Matches GPU_ARCH_MAJOR/MINOR and panthor_fw_load(), not a guessed SKU.
    return f"arm/mali/arch{gpu_id >> 28}.{(gpu_id >> 24) & 15}/mali_csffw.bin"


def source_contract(tree):
    base = tree / "drivers/gpu/drm/panthor"
    for name, sha in SOURCE_PINS.items():
        require(hashlib.sha256((base / name).read_bytes()).hexdigest() == sha,
                f"Panthor source changed: re-audit {name}")
    return dict(SOURCE_PINS)


def parse(data, page_size=4096):
    require(20 <= len(data) <= MAX_BYTES, "invalid binary size")
    require(page_size in (4096, 16384, 65536), "unsupported page-size preflight")
    magic, minor, major, pad, version_hash, pad2, table_end = struct.unpack_from("<IBBHIII", data)
    require(magic == 0xc3f13a6e and major == 0, "unsupported CSF binary header")
    # Padding and nonempty/unique shared sections are stricter than the native
    # parser; this preflight must not bless ambiguous mappings for activation.
    require(pad == 0 and pad2 == 0 and 20 <= table_end <= len(data) and table_end % 4 == 0,
            "invalid metadata table")
    sections, entries, skipped, build, shared = [], [], [], None, None
    offset = 20
    while offset < table_end:
        require(offset + 4 <= table_end, "truncated entry header")
        word = struct.unpack_from("<I", data, offset)[0]
        kind, size = word & 255, (word >> 8) & 255
        require(size >= 4 and size % 4 == 0 and offset + size <= table_end,
                "invalid entry size")
        entries.append({"offset": offset, "type": kind, "size": size,
                        "optional": bool(word & 0x80000000)})
        if kind == 0:
            require(size >= 24, "truncated section header")
            flags, va_start, va_end, start, end = struct.unpack_from("<5I", data, offset + 4)
            require(va_end >= va_start and end >= start and end <= len(data), "section bounds")
            require(va_start % page_size == 0 and va_end % page_size == 0,
                    "section not VM-page aligned")
            require(flags & ~SUPPORTED_FLAGS == 0, "unsupported section flags")
            if flags & 0x20:
                skipped.append({"offset": offset, "reason": "protected section ignored by Panthor"})
            else:
                require(end - start <= va_end - va_start, "initial data exceeds allocation")
                if va_start == SHARED_VA:
                    require(flags & 0x40000000 and va_end > va_start and shared is None,
                            "missing, duplicate or empty shared mapping")
                    shared = {"va_start": va_start, "va_end": va_end,
                              "data_start": start, "data_bytes": end - start}
                for prior in sections:
                    require(va_end <= prior["va_start"] or va_start >= prior["va_end"],
                            "overlapping active VA mappings")
                sections.append({"flags": flags, "va_start": va_start, "va_end": va_end,
                                 "data_start": start, "data_bytes": end - start})
        elif kind == 6:
            require(size >= 12, "truncated build metadata")
            start, count = struct.unpack_from("<II", data, offset + 4)
            require(count > 0 and start <= len(data) and count <= len(data) - start,
                    "build metadata bounds")
            raw = data[start:start + count]
            if raw.startswith(b"git_sha: ") and raw.endswith(b"\0"):
                candidate = raw[9:-1].strip()
                require(len(candidate) == 40 and
                        all(value in b"0123456789abcdef" for value in candidate),
                        "invalid build SHA metadata")
                build = candidate.decode("ascii")
        elif kind in (1, 2, 3, 4):
            skipped.append({"offset": offset, "reason": "known entry ignored by Panthor"})
        else:
            require(word & 0x80000000, "unknown mandatory entry")
            skipped.append({"offset": offset, "reason": "unknown optional entry"})
        offset += size
    require(shared is not None, "shared region missing")
    return {
        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
        "binary_header_version": f"{major}.{minor}", "version_hash": version_hash,
        "metadata_table_bytes": table_end, "build_git_sha": build,
        "active_sections": sections, "shared_region": shared,
        "mapped_bytes": sum(section["va_end"] - section["va_start"] for section in sections),
        "entries": entries, "ignored_entries": skipped,
        "format_preflight": "pass; conservative bounds beyond native parser",
        "runtime_interface": "unproven; firmware initializes shared control after MCU boot",
        "gpu_architecture_match": "requires powered GPU_ID, not derived from header version",
        "panthor_probe_is_read_only": False,
        "hardware_activation_permitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=B41_SHA)
    parser.add_argument("--gpu-id", type=lambda word: int(word, 0))
    args = parser.parse_args()
    try:
        pins = source_contract(args.kernel_tree)
        with args.image.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        require(hashlib.sha256(data).hexdigest() == args.expected_sha256, "asset SHA mismatch")
        report = parse(data)
        report["source_pins"] = pins
        if args.gpu_id is not None:
            report["request_firmware_relative_path"] = firmware_path(args.gpu_id)
            report["gpu_id_provenance"] = "caller supplied; not read by this checker"
    except Exception as error:
        parser.exit(1, f"CSF preflight failed ({type(error).__name__})\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
