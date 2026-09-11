#!/usr/bin/env python3
"""Mutation tests for static claims, never executable payload tests."""
from pathlib import Path
import struct
import sys

from audit import payload
from producer_audit import contracts

data = payload(Path(sys.argv[1]).read_bytes())
assert contracts(data)["active_table"] == "0x1985f8"
for offset, replacement in (
    (0x817f8, struct.pack("<I", 0xd503201f)),  # Changed getter
    (0x23b20, struct.pack("<I", 0xd2800020)),  # Earlier provider non-null
    (0x198600, struct.pack("<Q", 0xffff000050700000 + 0xc36ca)),  # Wrong partition
    (0x74f0c, struct.pack("<I", 0xd503201f)),  # Missing cert call
    (0x74f10, struct.pack("<I", 0xd503201f)),  # Missing cert failure edge
    (0x75088, struct.pack("<I", 0xd503201f)),  # Missing payload auth call
):
    changed = bytearray(data)
    changed[offset:offset + len(replacement)] = replacement
    try:
        contracts(changed)
    except ValueError:
        continue
    raise AssertionError(f"static contract accepted mutation at {offset:#x}")
print("PASS: exact producer contracts and six rejected getter/table/auth mutations")
