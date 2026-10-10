#!/usr/bin/env python3
"""Source/patch/profile parsing only locally; no C or instruction execution."""
import argparse
import ast
import hashlib
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
PL_SHA = "5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uboot", type=Path)
    parser.add_argument("--preloader-dump", type=Path)
    args = parser.parse_args()
    source = (HERE / "tetris_modem_linux_policy.c").read_text()
    assert 'tetris_modem_loaded_boot_once(fdt, user, slot, 1, "0", measured)' in source
    ordered = ["ret = require_slot_a(user)", "ret = selected_boot(user",
               "ret = preloader_digest(boot", "ret = tetris_modem_loaded_boot_once"]
    positions = [source.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert "if (unit == enabled)" in source and "seen != 1" in source
    assert "device->parent == user->bdev->parent" in source
    assert 'memcmp(buffer, "UFS_BOOT\\0", 9)' in source
    assert "size = word(buffer + 0x20)" in source
    assert "sha256_update(&sha, buffer, take)" in source
    assert "first_error ? first_error : -EALREADY" in source
    assert "blk_dwrite" not in source and "fdt_getprop" not in source
    patch = (HERE / "ufs-boot-identity.patch").read_text()
    assert "UPIU_QUERY_OPCODE_WRITE" not in patch
    assert "unit[4]" in patch and "QUERY_ATTR_IDN_BOOT_LU_EN" in patch
    capture = (HERE / "retained-handoff-storage.patch").read_text()
    positions = [capture.index(item) for item in (
        "tetris_modem_prepare_bundle_b41(buffer", "memcpy(footer, source",
        "release_ret = release_staging", "tetris_modem_sync_payloads(destination",
        "memcpy(check_header, footer, 512)" )]
    assert positions == sorted(positions)
    for f in HERE.glob("*.py"):
        ast.parse(f.read_text(), filename=str(f))
    if args.uboot:
        for name in ("ufs-boot-identity.patch", "retained-handoff-storage.patch"):
            subprocess.run(["git", "-C", str(args.uboot), "apply", "--check",
                            str(HERE / name)], check=True)
    if args.preloader_dump:
        data = args.preloader_dump.read_bytes()
        assert data[:9] == b"UFS_BOOT\0" and data[0x1000:0x1004] == b"MMM\x01"
        size = struct.unpack_from("<I", data, 0x1020)[0]
        assert 0x38 <= size <= 4 * 1024 * 1024 and size <= len(data) - 0x1000
        assert struct.unpack_from("<I", data, 0x101c)[0] == 0x02000f00
        assert hashlib.sha256(data[0x1000:0x1000 + size]).hexdigest() == PL_SHA
        print(f"PASS: stored pinned GFH source {size} bytes; NOT executing-image attestation")
    print("PASS: policy/UFS selection/GFH extent/footer lifetime static checks; NOT C execution")


if __name__ == "__main__":
    main()
