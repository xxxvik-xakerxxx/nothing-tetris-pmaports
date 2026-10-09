#!/usr/bin/env python3
"""CI-only native checks of the pinned GNSS callback/output boundaries."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "patches/gnss-navigation-audit"
VECTOR_SHA256 = "3ca6ab96e43f0dd4c7dca7ae8797f4e60ba92d944b39d0265a6d97f1f7d51468"


def build_run(root, name):
    binary = root / name
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(root / ("test_" + name + ".c")), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], cwd=root, capture_output=True)


def vectors_match(result):
    lines = result.stdout.splitlines()
    return (result.returncode == 0 and len(lines) == 262 and
            hashlib.sha256(b"\n".join(lines)).hexdigest() == VECTOR_SHA256)


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        names = ("b41_frame_sync", "b41_nmea_boundary")
        for name in names:
            shutil.copyfile(SOURCE / (name + ".h"), root / (name + ".h"))
            shutil.copyfile(SOURCE / ("test_" + name + ".c"), root / ("test_" + name + ".c"))
        frames = build_run(root, names[0])
        if not vectors_match(frames):
            raise RuntimeError("GNSS callback vectors differ from pinned B4.1 emulation")
        output = build_run(root, names[1])
        if output.returncode:
            raise RuntimeError("GNSS registration/output boundary failed")
        print(output.stdout.decode().strip())
        mutants = ((names[0], "value & 255u", "value"),
                   (names[1], "const unsigned required = 0x3fb;",
                    "const unsigned required = 0;"),
                   (names[1], "memmove(dst, src, length);", "memset(dst, 0, length);"))
        for name, old, new in mutants:
            text = (SOURCE / (name + ".h")).read_text()
            if old not in text:
                raise RuntimeError("missing GNSS mutation anchor")
            (root / (name + ".h")).write_text(text.replace(old, new))
            result = build_run(root, name)
            accepted = vectors_match(result) if name == names[0] else result.returncode == 0
            if accepted:
                raise RuntimeError("GNSS boundary accepted a broken implementation")
            (root / (name + ".h")).write_text(text)
        print("PASS: 262 pinned GNSS callback vectors and three negative mutants; no device access")


if __name__ == "__main__":
    main()
