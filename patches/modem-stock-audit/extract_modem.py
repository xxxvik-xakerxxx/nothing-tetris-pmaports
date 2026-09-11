#!/usr/bin/env python3
"""Extract only modem.img after verifying the entire existing local archive."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ARCHIVE_SHA = "2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811"
folder = Path(__file__).resolve().parent
archive = Path(sys.argv[1]).resolve()
with archive.open("rb") as source:
    digest = hashlib.file_digest(source, "sha256").hexdigest()
if digest != ARCHIVE_SHA:
    raise SystemExit("archive SHA-256 mismatch; extraction refused")
local = folder / "local"
local.mkdir(exist_ok=True)
temporary = None
try:
    with tempfile.NamedTemporaryFile(prefix="modem-", suffix=".partial", dir=local,
                                     delete=False) as output:
        temporary = Path(output.name)
        process = subprocess.Popen(["7zz", "x", "-so", str(archive), "modem.img"],
                                   stdout=subprocess.PIPE)
        try:
            size = 0
            while chunk := process.stdout.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise ValueError("member exceeds offline extraction bound")
                output.write(chunk)
            if process.wait():
                raise ValueError("archive extraction failed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    with temporary.open("rb") as source:
        image_sha = hashlib.file_digest(source, "sha256").hexdigest()
    target = local / "modem.img"
    if target.exists():
        with target.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != image_sha:
                raise ValueError("different existing modem.img; refusing replacement")
        temporary.unlink()
    else:
        temporary.rename(target)
    result = dict(archive_sha256=digest, member="modem.img", size=size,
                  sha256=image_sha, provenance="local archive hash; no signature or slot validation")
    (folder / "modem-input.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
finally:
    if temporary is not None:
        temporary.unlink(missing_ok=True)
