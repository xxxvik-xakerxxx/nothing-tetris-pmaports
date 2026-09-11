#!/usr/bin/env python3
"""Run the C locator on an ignored, read-only real container; save metadata only."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import shlex
import subprocess
import struct
import tempfile

folder = Path(__file__).resolve().parent
path = folder / "local/modem.img"
expected = json.loads((folder / "modem-input.json").read_text())
with path.open("rb") as source:
    digest = hashlib.file_digest(source, "sha256").hexdigest()
if digest != expected["sha256"] or path.stat().st_size != expected["size"]:
    raise SystemExit("extracted input identity mismatch")
with tempfile.TemporaryDirectory(prefix="probe-", dir=folder / "local") as tmp:
    binary = Path(tmp) / "probe"
    subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        str(folder / "modem_image.c"), str(folder / "probe_modem_image.c"),
        "-o", str(binary)], check=True)
    result = json.loads(subprocess.run([str(binary), str(path)],
                        capture_output=True, text=True, check=True).stdout)
with path.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
    headers, offset = [], 0
    for _ in range(128):
        if len(data) - offset < 512 or struct.unpack_from("<I", data, offset)[0] != 0x58881688:
            break
        length = struct.unpack_from("<I", data, offset + 4)[0]
        alignment = struct.unpack_from("<I", data, offset + 0x44)[0]
        if not alignment or alignment & (alignment - 1):
            raise ValueError("invalid real member alignment")
        name = data[offset + 8:offset + 40].split(b"\0", 1)[0].decode("ascii")
        end = offset + 512 + ((length + alignment - 1) & ~(alignment - 1))
        if end > len(data):
            raise ValueError("real member exceeds container")
        headers.append(dict(offset=offset, name=name, size=length, alignment=alignment))
        offset = end
    for member in result:
        if member["result"] == 0:
            start, size = member["payload_offset"], member["payload_size"]
            if start < 0 or size <= 0 or start + size > len(data):
                raise ValueError("invalid C locator output")
            member["sha256"] = hashlib.sha256(memoryview(data)[start:start + size]).hexdigest()
    after = hashlib.sha256(data).hexdigest()
if after != digest:
    raise ValueError("container changed during probe")
output = dict(container_sha256=digest, unchanged=True, members=result,
              authentication="not performed", active_slot="not inferred",
              header_walk=headers, walk_end=offset, remaining_bytes=expected["size"] - offset)
(folder / "modem-real-result.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(output, indent=2))
