#!/usr/bin/env python3
"""Compile packaged candidate translation units in CI, never install them."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request


PACKAGE = Path("pmaports/device/testing/linux-postmarketos-mediatek-mt6878")
CONFIG = "config-postmarketos-mediatek-mt6878.aarch64"
MODULES = (
    "VIDEO_IMX882_TETRIS", "VIDEO_MT6878_SENINF_GRAPH",
    "MTK_MT6878_CCCI_FIRST_START", "MTK_MT6878_GPUEB_POWER",
)
ENABLE = (
    "MEDIA_SUPPORT", "MEDIA_CAMERA_SUPPORT", "VIDEO_DEV",
    "MEDIA_PLATFORM_SUPPORT", "MEDIA_PLATFORM_DRIVERS",
    "MEDIA_CONTROLLER", "VIDEO_V4L2_SUBDEV_API", "V4L2_FWNODE",
)
OBJECTS = (
    "drivers/media/i2c/imx882-tetris-stream.o",
    "drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.o",
    "drivers/media/platform/mediatek/seninf/mt6878-seninf-phy-smoke.o",
    "drivers/soc/mediatek/mt6878-ccci-start.o",
    "drivers/pmdomain/mediatek/mt6878-gpueb-power.o",
)
STRICT_PATCHES = frozenset((
    "0116-media-platform-mediatek-mt6878-seninf-phy-backend.patch",
    "0117-soc-mediatek-mt6878-ccci-first-start-backend.patch",
    "0118-pmdomain-mediatek-mt6878-gpueb-power-backend.patch",
))


def block(source, key):
    matches = re.findall(rf'^{key}="\n(.*?)^"$', source, re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f"expected one literal {key} block")
    return matches[0]


def plan(package):
    source = (package / "APKBUILD").read_text()
    commits = re.findall(r'^_commit="([0-9a-f]{40})"$', source, re.M)
    if len(commits) != 1:
        raise ValueError("kernel source must have an immutable commit")
    commit = commits[0]
    entries = block(source, "source").split()
    if entries[0] != "$pkgname-$_commit.tar.gz::https://github.com/MT6878-mainline/$_repository/archive/$_commit.tar.gz":
        raise ValueError("unsupported kernel archive expression")
    hashes = {}
    for row in block(source, "sha512sums").splitlines():
        if not row.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{128})  ([A-Za-z0-9_.-]+)", row.strip())
        if not match or match[2] in hashes:
            raise ValueError("invalid or duplicate package checksum")
        hashes[match[2]] = match[1]
    patches = [entry for entry in entries if entry.endswith(".patch")]
    if not patches or len(set(patches)) != len(patches):
        raise ValueError("empty or duplicated kernel patch stack")
    for name in [CONFIG, *patches]:
        if Path(name).name != name or name not in hashes:
            raise ValueError(f"untracked package source: {name}")
        if hashlib.sha512((package / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"package checksum mismatch: {name}")
    archive = f"linux-postmarketos-mediatek-mt6878-{commit}.tar.gz"
    return {"kernel_commit": commit, "archive": archive,
            "archive_sha512": hashes[archive], "patches": patches,
            "source_sha512": {name: hashes[name] for name in [CONFIG, *patches]},
            "application": "package default for historical stack; fuzz=0 for new backends",
            "objects": OBJECTS, "module_options": MODULES}


def run(command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True)


def object_identity(target):
    with target.open("rb") as stream:
        magic = stream.read(4)
    if magic in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
        # Shipping ThinLTO emits LLVM IR for built-in translation units.
        ir = subprocess.check_output(["llvm-dis", "-o", "-", target], text=True)
        triples = re.findall(r'^target triple = "([^"]+)"$', ir, re.M)
        if len(triples) != 1 or not triples[0].startswith("aarch64-"):
            raise ValueError(f"wrong bitcode architecture: {target.name}")
        return {"format": "LLVM bitcode", "target_triple": triples[0]}
    header = subprocess.check_output(["llvm-readelf", "-h", target], text=True)
    if magic != b"\x7fELF" or not re.search(r"Machine:\s+AArch64", header):
        raise ValueError(f"wrong object architecture: {target.name}")
    return {"format": "ELF", "machine": "AArch64"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--work", type=Path, default=Path("/tmp/tetris-kernel-smoke"))
    args = parser.parse_args()
    package = PACKAGE.resolve()
    manifest = plan(package)
    if args.plan_only:
        print(json.dumps(manifest, indent=2))
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("native kernel compilation is CI-only")
    args.work.mkdir(parents=True, exist_ok=False)
    report = Path("out/kernel-object-smoke")
    report.mkdir(parents=True, exist_ok=True)
    manifest.update(commit=os.environ["GITHUB_SHA"], status="started",
                    scope="object-only; no linking, installation or hardware test")
    manifest_file = report / "BUILD-MANIFEST.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    archive = args.work / manifest["archive"]
    url = f'https://github.com/MT6878-mainline/linux/archive/{manifest["kernel_commit"]}.tar.gz'
    with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as dest:
        shutil.copyfileobj(response, dest)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != manifest["archive_sha512"]:
            raise ValueError("kernel archive checksum mismatch")
    with tarfile.open(archive) as tar:
        tar.extractall(args.work, filter="data")
    kernel = args.work / f'linux-{manifest["kernel_commit"]}'
    for patch in manifest["patches"]:
        # Match abuild default_prepare for legacy patches, not a different build.
        flags = ["--fuzz=0"] if patch in STRICT_PATCHES else []
        run(["patch", "--batch", *flags, "-p1", "-d", kernel, "-i", package / patch])
    output = args.work / "objects"
    output.mkdir()
    shutil.copyfile(package / CONFIG, output / ".config")
    options = [kernel / "scripts/config", "--file", output / ".config"]
    for symbol in ENABLE:
        options.extend(["-e", symbol])
    for symbol in MODULES:
        options.extend(["-m", symbol])
    run(options)
    make = ["make", "-C", kernel, f"O={output}", "ARCH=arm64", "LLVM=1", "-j4"]
    run([*make, "olddefconfig"])
    shutil.copyfile(output / ".config", report / "isolated.config")
    config = (output / ".config").read_text().splitlines()
    for symbol in MODULES:
        if f"CONFIG_{symbol}=m" not in config:
            raise ValueError(f"isolated dependency missing: {symbol}")
    run([*make, "-k", *OBJECTS])
    identities = {}
    for name in OBJECTS:
        target = output / name
        if not target.is_file() or not target.stat().st_size:
            raise ValueError(f"missing object: {name}")
        identities[name] = object_identity(target)
        identities[name]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(name + ": " + json.dumps(identities[name]), flush=True)
    if list(output.rglob("*.ko")) or (output / "vmlinux").exists():
        raise ValueError("object-only CI must not produce runtime modules or kernel")
    manifest["status"] = "passed"
    manifest["object_identities"] = identities
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
