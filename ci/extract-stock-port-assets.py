#!/usr/bin/env python3
"""Extract selected generic B4.1 vendor/system assets as data, never execute them."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
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
MAX_IMAGE = 4 * 1024 * 1024 * 1024
MAX_LIBLOG = 16 * 1024 * 1024
# Same pinned logical archive: root-level member verified in cached CI listing.
SYSTEM_IMAGE_SIZE = 1039855616
SYSTEM_LIBLOG_PATHS = ("/system/lib64/liblog.so", "/lib64/liblog.so")
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


def select_image(listing, name):
    candidates = []
    for block in listing.split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        member = fields.get("Path", "")
        if Path(member).name != name:
            continue
        size = int(fields.get("Size", "0"))
        if (member != name or not 0 < size <= MAX_IMAGE or
                fields.get("Folder") == "+" or "Symbolic Link" in fields or
                "Hard Link" in fields or
                any(token.startswith(("l", "d", "b", "c", "p", "s"))
                    for token in fields.get("Attributes", "").split())):
            raise ValueError("unsafe or nonregular archive image")
        candidates.append((member, size))
    if len(candidates) != 1:
        raise ValueError(f"expected one root-level {name}")
    if name == "system.img" and candidates[0][1] != SYSTEM_IMAGE_SIZE:
        raise ValueError("pinned system image size mismatch")
    return candidates[0]


def filesystem(image):
    with image.open("rb") as stream:
        stream.seek(1024)
        erofs_magic = stream.read(4)
        stream.seek(1080)
        ext4_magic = stream.read(2)
    if erofs_magic == b"\xe2\xe1\xf5\xe0":
        return "erofs"
    if ext4_magic == b"\x53\xef":
        return "ext4"
    raise ValueError("unsupported stock filesystem")


def extract_system_liblog(raw, kind, work, target):
    """Only two explicit system-root layouts; no recursive system extraction."""
    if kind not in ("ext4", "erofs"):
        raise ValueError("unsupported system filesystem")
    if kind == "erofs":
        help_text = subprocess.check_output(["dump.erofs", "--help"], text=True,
                                            stderr=subprocess.STDOUT)
        if "--cat" not in help_text:
            raise ValueError("selective system extraction requires dump.erofs --cat")
    found = []
    for index, name in enumerate(SYSTEM_LIBLOG_PATHS):
        candidate = work / f"system-liblog-{index}"
        if kind == "ext4":
            metadata = subprocess.check_output(["debugfs", "-R", f"stat {name}", str(raw)],
                                               text=True)
            if "Inode:" not in metadata:
                continue
            file_type = re.search(r"Type:\s+(\w+)", metadata)
            file_size = re.search(r"\bSize:\s+(\d+)", metadata)
            if (not file_type or file_type[1] != "regular" or not file_size or
                    not 0 < int(file_size[1]) <= MAX_LIBLOG):
                raise ValueError("invalid system liblog inode")
            # No -w, no mount, no executing data from the image.
            subprocess.run(["debugfs", "-R", f"dump {name} {candidate}", str(raw)],
                           check=True, stdout=subprocess.DEVNULL)
        else:
            with candidate.open("xb") as output:
                process = subprocess.Popen(["dump.erofs", f"--path={name}", "--cat", str(raw)],
                                           stdout=subprocess.PIPE)
                try:
                    data = process.stdout.read(MAX_LIBLOG + 1)
                    if len(data) > MAX_LIBLOG:
                        raise ValueError("oversized system liblog")
                    result = process.wait()
                    if not result:
                        output.write(data)
                finally:
                    process.stdout.close()
                    if process.poll() is None:
                        process.kill()
                    process.wait()
        if not candidate.exists():
            continue
        info = candidate.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_LIBLOG:
            raise ValueError("invalid selected system liblog")
        if info.st_size:
            found.append((name, candidate))
    if len(found) != 1:
        raise ValueError("expected exactly one system liblog layout")
    name, candidate = found[0]
    exports = audit_liblog(candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output, candidate.open("rb") as source:
        shutil.copyfileobj(source, output)
    target.chmod(0o644)
    return {"image_path": name, "exports": exports}


def audit_liblog(path):
    # Read ELF metadata only; source identity comes from the pinned archive,
    # not from an NDK SONAME/import stub or executing the selected library.
    from elftools.elf.elffile import ELFFile
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 64 or not elf.little_endian or \
                elf["e_machine"] != "EM_AARCH64" or elf["e_type"] != "ET_DYN":
            raise ValueError("system liblog is not an ARM64 shared implementation")
        dynamic = elf.get_section_by_name(".dynamic")
        if dynamic is None or [t.soname for t in dynamic.iter_tags()
                               if t.entry.d_tag == "DT_SONAME"] != ["liblog.so"]:
            raise ValueError("wrong system liblog SONAME")
        definitions = elf.get_section_by_name(".gnu.version_d")
        versions = elf.get_section_by_name(".gnu.version")
        symbols = elf.get_section_by_name(".dynsym")
        if definitions is None or versions is None or symbols is None:
            raise ValueError("missing LIBLOG symbol definitions")
        names = {v.entry.vd_ndx: next(aux).name for v, aux in definitions.iter_versions()}
        exports = {}
        for index, symbol in enumerate(symbols.iter_symbols()):
            if symbol.name not in ("__android_log_buf_write", "__android_log_assert"):
                continue
            version = versions.get_symbol(index).entry.ndx
            executable = any(segment["p_type"] == "PT_LOAD" and segment["p_flags"] & 1 and
                segment["p_vaddr"] <= symbol["st_value"] and
                symbol["st_value"] + symbol["st_size"] <= segment["p_vaddr"] + segment["p_filesz"]
                for segment in elf.iter_segments())
            if (not isinstance(version, int) or version & 0x8000 or names.get(version) != "LIBLOG" or
                    symbol["st_shndx"] == "SHN_UNDEF" or symbol["st_size"] == 0 or
                    symbol["st_info"]["type"] != "STT_FUNC" or
                    symbol["st_info"]["bind"] not in ("STB_GLOBAL", "STB_WEAK") or
                    symbol["st_other"]["visibility"] not in ("STV_DEFAULT", "STV_PROTECTED") or
                    not executable or symbol.name in exports):
                raise ValueError("invalid LIBLOG implementation export")
            exports[symbol.name] = "LIBLOG"
        if len(exports) != 2:
            raise ValueError("required LIBLOG exports absent")
        return exports


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
    images = [select_image(listing, name) for name in ("vendor.img", "system.img")]
    run("7z", "x", "-y", f"-o{work / 'image'}", archive, *(name for name, _ in images))
    for name, size in images:
        selected = work / "image" / name
        if not stat.S_ISREG(selected.lstat().st_mode) or selected.stat().st_size != size:
            raise ValueError("invalid selected image")
    image = work / "image" / "vendor.img"
    system_image = work / "image" / "system.img"
    manifest["vendor_image_sha256"] = digest(image)
    manifest["system_image_sha256"] = digest(system_image)
    # Both selected images now exist; never redownload the OTA for system.
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
    with system_image.open("rb") as stream:
        sparse = stream.read(4) == struct.pack("<I", 0xed26ff3a)
    if sparse:
        system_raw = work / "system.raw"
        run("simg2img", system_image, system_raw)
        system_image.unlink()
    else:
        system_raw = system_image
    kind = filesystem(system_raw)
    manifest["system_filesystem"] = kind
    if kind == "erofs":
        manifest["system_extractor"] = {
            "source_commit": os.environ["TETRIS_EROFS_TOOLS_COMMIT"],
            "version": subprocess.check_output(["dump.erofs", "--version"], text=True).strip(),
        }
    target = out / "system/lib64/liblog.so"
    manifest["system_liblog"] = extract_system_liblog(system_raw, kind, work, target)
    manifest["files"].append({"path": "system/lib64/liblog.so", "size": target.stat().st_size,
                              "sha256": digest(target)})
    manifest["status"] = "extracted; identity matched; runtime contracts untested"
    manifest["trust"] = "pinned mirror hashes plus independent libMNL pin; not OEM signature verification"
    (out / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
