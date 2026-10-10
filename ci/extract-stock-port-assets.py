#!/usr/bin/env python3
"""Extract selected generic B4.1 vendor assets as data, never execute them."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

RELEASE = "Tetris_B4.1-260415-1709"
BASE = f"https://github.com/spike0en/nothing_archive/releases/download/{RELEASE}"
PARTS = (
    ("001", 2097152000, "35a72dfafe45c4939612c09ede81dddb0012e0fa95759e01cb7f4b12f335da6a"),
    ("002", 1574303572, "d718a556a38ef82aab9e0e99777aac5f7ca4a26e56640e63eec02fde0aaa2cc8"),
)
LIBMNL_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
NAMES = ["build.prop", "etc/MNL_Config.xml", "bin/mnld", "firmware/mali_csffw.bin",
         "etc/init/camerahalserver.rc", "etc/vintf/manifest/manifest_cameraprovider.xml",
         "etc/vintf/manifest/manifest_isphal.xml"]
for prefix in ("", "mt6878/"):
    NAMES.append("bin/hw/" + prefix + "camerahalserver")
    for library in ("libmnl.so", "libmipc.so", "libmtkrillog.so", "libtrm.so",
                    "libmtkproperty.so", "libccd.so", "libispinterpreter_mtkcam.so",
                    "libispfeature_mtkcam.v4l2.so", "libcam.halisp.imp.v4l2.so",
                    "libcam.halisp.v4l2.so", "libcam.halisp.TopCtrlMgr.so"):
        NAMES.append("lib64/" + prefix + library)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*command):
    subprocess.run(list(map(str, command)), check=True)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("large stock-image extraction is CI-only")
    work = Path("/tmp/tetris-stock-port-assets")
    work.mkdir(exist_ok=False)
    out = Path("out/stock-port-assets")
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"release": RELEASE, "source": BASE, "commit": os.environ["GITHUB_SHA"],
                "scope": "generic stock data, no execution, no handset NV/calibration",
                "status": "started", "archives": [], "files": [], "missing": []}
    for suffix, size, expected in PARTS:
        name = f"{RELEASE}-image-logical.7z.{suffix}"
        path = work / name
        run("curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
            "--output", path, BASE + "/" + name)
        if path.stat().st_size != size or digest(path) != expected:
            raise ValueError("stock archive identity mismatch")
        manifest["archives"].append({"name": name, "size": size, "sha256": expected})
    archive = work / f"{RELEASE}-image-logical.7z.001"
    listing = subprocess.check_output(["7z", "l", "-slt", str(archive)], text=True)
    (out / "archive-listing.txt").write_text(listing)
    images = [line.removeprefix("Path = ") for line in listing.splitlines()
              if line.startswith("Path = ") and Path(line.removeprefix("Path = ")).name == "vendor.img"]
    if len(images) != 1:
        raise ValueError("expected one vendor image")
    relative = Path(images[0])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe archive path")
    run("7z", "x", "-y", f"-o{work / 'image'}", archive, images[0])
    image = work / "image" / relative
    if not image.is_file() or image.is_symlink():
        raise ValueError("invalid vendor image")
    manifest["vendor_image_sha256"] = digest(image)
    for suffix, _, _ in PARTS:
        (work / f"{RELEASE}-image-logical.7z.{suffix}").unlink()
    with image.open("rb") as stream:
        magic = struct.unpack("<I", stream.read(4))[0]
    if magic == 0xed26ff3a:
        raw = work / "vendor.raw"
        run("simg2img", image, raw)
        image.unlink()
    else:
        raw = image
    with raw.open("rb") as stream:
        stream.seek(1024)
        erofs_magic = stream.read(4)
        stream.seek(1080)
        ext4_magic = stream.read(2)
    erofs = work / "erofs"
    if erofs_magic == b"\xe2\xe1\xf5\xe0":
        run("fsck.erofs", f"--extract={erofs}", raw)
        kind = "erofs"
    elif ext4_magic == b"\x53\xef":
        kind = "ext4"
    else:
        raise ValueError("unsupported vendor filesystem")
    manifest["filesystem"] = kind
    for name in NAMES:
        target = out / "vendor" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "ext4":
            # debugfs is read-only without -w; only fixed audit paths are used.
            subprocess.run(["debugfs", "-R", f"dump /{name} {target}", str(raw)],
                           check=True, stdout=subprocess.DEVNULL)
        else:
            source = erofs / name
            if source.is_file() and not source.is_symlink():
                shutil.copyfile(source, target)
        if not target.is_file():
            manifest["missing"].append(name)
            continue
        if target.is_symlink() or target.stat().st_size > 256 * 1024 * 1024:
            raise ValueError("invalid selected stock asset")
        target.chmod(0o644)
        manifest["files"].append({"path": "vendor/" + name,
                                  "size": target.stat().st_size, "sha256": digest(target)})
    if not any(row["sha256"] == LIBMNL_SHA and row["path"].endswith("/libmnl.so")
               for row in manifest["files"]):
        raise ValueError("vendor release does not match independently pinned B4.1 libMNL")
    manifest["status"] = "extracted; identity matched; runtime contracts untested"
    manifest["trust"] = "pinned mirror hashes plus independent libMNL pin; not OEM signature verification"
    (out / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
