#!/usr/bin/env python3
"""CI-only extraction of one public stock modem image, never handset NV."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

RELEASE = "Tetris_B4.1-260415-1709"
ARCHIVE = f"{RELEASE}-image-firmware.7z"
ARCHIVE_SIZE = 59168898
ARCHIVE_SHA256 = "2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811"
BASE = f"https://github.com/spike0en/nothing_archive/releases/download/{RELEASE}"
MAX_IMAGE = 256 * 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def select_image(listing):
    candidates = []
    for block in listing.split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        name = fields.get("Path", "")
        path = Path(name)
        if path.name not in ("md1img.img", "md1img.bin"):
            continue
        size = int(fields.get("Size", "0"))
        if (path.is_absolute() or ".." in path.parts or "\\" in name or
                not 0 < size <= MAX_IMAGE or fields.get("Folder") == "+" or
                "Symbolic Link" in fields or "Hard Link" in fields):
            raise ValueError("invalid stock modem member")
        candidates.append((name, size))
    if len(candidates) != 1:
        raise ValueError("expected exactly one stock md1img member")
    return candidates[0]


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("stock modem extraction is CI-only")
    output = Path("out/stock-modem")
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="tetris-stock-modem-") as temporary:
        archive = Path(temporary) / ARCHIVE
        subprocess.run(["curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
                        "--max-time", "300", "--output", str(archive), BASE + "/" + ARCHIVE],
                       check=True)
        if archive.stat().st_size != ARCHIVE_SIZE or digest(archive) != ARCHIVE_SHA256:
            raise ValueError("stock firmware archive identity mismatch")
        listing = subprocess.check_output(["7z", "l", "-slt", str(archive)], text=True)
        name, size = select_image(listing)
        image = output / "md1img.bin"
        with image.open("xb") as stream:
            subprocess.run(["7z", "e", "-so", str(archive), name], stdout=stream, check=True)
        if image.stat().st_size != size:
            raise ValueError("stock modem extracted size mismatch")
        manifest = {
            "release": RELEASE, "source_commit": os.environ["GITHUB_SHA"],
            "archive": ARCHIVE, "archive_sha256": ARCHIVE_SHA256,
            "member": name, "size": size, "sha256": digest(image),
            "scope": "public firmware only; no handset NV/calibration or execution",
            "trust": "mirror identity; OEM signature verification is a separate required test",
        }
        (output / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
