#!/usr/bin/env python3
"""CI-only compiled decoder comparison to locally proven stock producer layout."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

def expected(node):
    result = bytearray(0xfc4)
    name = node.text.strip().encode()
    result[:len(name)] = name
    struct.pack_into("<d", result, 0x14, float(node.findtext("version")))
    result[0x1c] = int(node.findtext("config"))
    total = 0
    for row, setting in enumerate(node.findall("setting")):
        values = [float(v) for v in setting.text.split(",")]
        total += len(values)
        struct.pack_into("<" + "d" * len(values), result, 0x24 + row * 200, *values)
    struct.pack_into("<I", result, 0x20, total)
    return result

def main(binary, asset):
    raw = asset.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31"
    nodes = ET.fromstring(raw).findall("feature")
    assert len(nodes) == 19
    for node in nodes:
        run = subprocess.run([str(binary), str(asset), node.text.strip()], check=True, capture_output=True)
        assert run.stdout == expected(node), node.text.strip()
    print("PASS: 19 stock XML ABI results and native failure/immutable-output fixtures")

if __name__ == "__main__": main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
