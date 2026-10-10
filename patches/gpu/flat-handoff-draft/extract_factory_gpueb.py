#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""CI-only public B4.1 gpueb member; never device dumps or decrypted content."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gpueb_firmware as firmware

RELEASE = "Tetris_B4.1-260415-1709"
ARCHIVE = RELEASE + "-image-firmware.7z"
URL = "https://github.com/spike0en/nothing_archive/releases/download/" + RELEASE + "/" + ARCHIVE
ARCHIVE_SIZE = 59168898
ARCHIVE_SHA = "2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811"
SIZE = 532480
SHA = "58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22"
ROOT = "e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e"


def verify(path, size, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError("input type/size mismatch")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("input digest mismatch")


def member(listing):
    found = []
    for block in listing.split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        name = fields.get("Path", "")
        path = Path(name)
        if path.name != "gpueb.img":
            continue
        if (path.is_absolute() or ".." in path.parts or "\\" in name or
                any(ord(c) < 32 for c in name) or name.startswith("-") or
                fields.get("Size") != str(SIZE) or fields.get("Folder") == "+" or
                "Symbolic Link" in fields or "Hard Link" in fields):
            raise ValueError("unsafe/non-matching gpueb archive member")
        found.append(name)
    if len(found) != 1:
        raise ValueError("expected exactly one gpueb.img member")
    return found[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, help="reuse verified CI firmware archive")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("public archive download/extraction is CI-only")
    args.out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="tetris-factory-gpueb-") as temporary:
        archive = args.archive or Path(temporary) / ARCHIVE
        if args.archive is None:
            subprocess.run(["curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
                            "--max-time", "300", "--output", str(archive), URL], check=True)
        verify(archive, ARCHIVE_SIZE, ARCHIVE_SHA)
        name = member(subprocess.check_output(["7z", "l", "-slt", str(archive)], text=True))
        output = args.out / "gpueb.img"
        try:
            with output.open("xb") as stream:
                subprocess.run(["7z", "e", "-so", str(archive), name], stdout=stream, check=True)
            verify(output, SIZE, SHA)
            result = firmware.inspect(output.read_bytes(), ROOT)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        manifest = {
            "release": RELEASE, "source": URL, "source_commit": os.environ["GITHUB_SHA"],
            "archive_size": ARCHIVE_SIZE,
            "archive_sha256": ARCHIVE_SHA, "member": name, "size": SIZE, "sha256": SHA,
            "root_spki_sha256": ROOT, "primary_authenticated_bytes": 156064,
            "primary_plaintext_sha256": "4cd3ac60605b30f92988a7606e95b7e4f82d70513bbd12923a0e562e9fc31702",
            "authentication": result,
            "scope": "public factory ciphertext only; no handset NV/keys/plaintext; no execution",
        }
        (args.out / "PROVENANCE.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
