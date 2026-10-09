#!/usr/bin/env python3
"""CI-only repackaging of immutable boot inputs for one read-only GPU probe."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile

from check_diagnostic_dt import read_tree, validate_trees

IMAGES = ("kernel", "fdt", "initrd")
FILES = ("vmlinuz", "mt6878-nothing-tetris-native.dtb", "initramfs")
FIT_NAME = "boot_image-vgpu-observe-diagnostic.itb"
BOOT_NAME = "nothing-tetris-boot-vgpu-observe-diagnostic.img"
MODES = ("vgpu-observe", "modem-preflight")


def artifact_names(mode):
    require(mode in MODES, "Unknown diagnostic mode")
    return f"boot_image-{mode}-diagnostic.itb", f"nothing-tetris-boot-{mode}-diagnostic.img"


def load_modem_checker():
    path = Path(__file__).resolve().parents[1] / "modem/check_preflight_dt.py"
    spec = importlib.util.spec_from_file_location("tetris_modem_preflight_checker", path)
    require(spec is not None and spec.loader is not None, "Modem DT checker is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_mode(mode, normal, diagnostic, baseline=None):
    if mode == "vgpu-observe":
        require(baseline is None, "--baseline-dtb is supported only for modem-preflight")
        return validate_trees(read_tree(normal), read_tree(diagnostic))
    require(mode == "modem-preflight", "Unknown diagnostic mode")
    checker = load_modem_checker()
    if baseline is not None:
        require(callable(getattr(checker, "check_native_baseline", None)),
                "Modem normal-to-OFF checker export is not ready")
        checker.check_native_baseline(read_tree(normal), read_tree(baseline))
    return checker.validate_trees(read_tree(baseline or normal), read_tree(diagnostic))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Commands:
    def __init__(self):
        self.records = []

    def __call__(self, args, cwd=None):
        result = subprocess.run([str(arg) for arg in args], cwd=cwd,
                                text=True, capture_output=True)
        self.records.append({"argv": [str(arg) for arg in args],
                             "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {args!r}\n{result.stderr}")
        return result.stdout


def fdt_value(run, fit, node, prop):
    raw = run(["fdtget", "-t", "bx", fit, node, prop])
    return bytes(int(byte, 16) for byte in raw.split())


def fit_metadata(run, fit):
    """Do not materialize large FIT payloads as hexadecimal fdtget output."""
    require(run(["fdtget", "-l", fit, "/"]).splitlines() == ["images", "configurations"],
            "Unexpected FIT root children")
    require(run(["fdtget", "-l", fit, "/images"]).splitlines() == list(IMAGES),
            "FIT child order must be kernel/fdt/initrd for dumpimage indexes")
    require(run(["fdtget", "-l", fit, "/configurations"]).splitlines() == ["native-display"],
            "Unexpected FIT configurations")
    nodes = ["/", "/images", "/configurations", "/configurations/native-display"]
    nodes += ["/images/" + name for name in IMAGES]
    metadata = {}
    for node in nodes:
        properties = set(run(["fdtget", "-p", fit, node]).splitlines())
        if node.startswith("/images/"):
            require(not run(["fdtget", "-l", fit, node]).strip(),
                    "Unexpected image hashes/signatures/subnodes")
            expected = {"description", "data", "type", "arch", "compression", "load", "entry"}
            if node != "/images/fdt":
                expected.add("os")
            require(properties == expected, "Unexpected inline FIT image properties: " + node)
        elif node == "/":
            require(properties in ({"description", "#address-cells"},
                                   {"description", "#address-cells", "timestamp"}),
                    "Unexpected FIT root properties")
        elif node == "/images":
            require(not properties, "Unexpected images-container properties")
        elif node == "/configurations":
            require(properties == {"default"}, "Unexpected configuration-container properties")
        else:
            require(properties == {"description", "kernel", "fdt", "ramdisk"},
                    "Unexpected configuration properties")
        metadata[node] = {prop: fdt_value(run, fit, node, prop)
                          for prop in properties - {"data", "timestamp"}}
    require(metadata["/"]["#address-cells"] == struct.pack(">I", 1), "FIT address-cell mismatch")
    require(metadata["/configurations"]["default"] == b"native-display\0", "FIT default mismatch")
    config = metadata["/configurations/native-display"]
    require(all(config[key] == value for key, value in {
        "kernel": b"kernel\0", "fdt": b"fdt\0", "ramdisk": b"initrd\0"}.items()),
        "FIT configuration references mismatch")
    for name, kind, compression, address in (
        ("kernel", "kernel", "gzip", 0x42000000),
        ("fdt", "flat_dt", "none", 0x47000000),
        ("initrd", "ramdisk", "none", 0x45500000),
    ):
        data = metadata["/images/" + name]
        require(data["type"] == kind.encode() + b"\0" and data["arch"] == b"arm64\0"
                and data["compression"] == compression.encode() + b"\0", "FIT image ABI mismatch")
        require(data["load"] == struct.pack(">I", address)
                and data["entry"] == struct.pack(">I", address), "FIT load/entry mismatch")
        if name != "fdt":
            require(data["os"] == b"linux\0", "FIT OS mismatch")
    return metadata


def extract_fit(run, fit, directory):
    directory.mkdir()
    result = []
    for index, filename in enumerate(FILES):
        path = directory / filename
        run(["dumpimage", "-T", "flat_dt", "-p", str(index), "-o", path, fit])
        require(path.is_file() and path.stat().st_size > 0, "FIT extraction produced no data")
        result.append(path)
    return result


def ext_format(path):
    with path.open("rb") as stream:
        header = stream.read(2048)
    if len(header) < 2048 or header[1080:1082] != b"\x53\xef":
        return None
    if header[:4] == b"\x3a\xff\x26\xed" or header[510:512] == b"\x55\xaa":
        return None
    compat, incompat = struct.unpack_from("<II", header, 1116)
    return "ext4" if incompat & 0x40 else "ext3" if compat & 4 else "ext2"


def inventory(directory):
    result = {}
    for path in directory.rglob("*"):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            result[relative] = ("directory",)
        elif path.is_file():
            result[relative] = ("file", sha256(path))
        else:
            raise ValueError("Unexpected special file in boot filesystem: " + relative)
    return result


def quote_debugfs(path):
    text = str(path)
    require(not any(ord(char) < 32 for char in text), "Control character in debugfs path")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fit_inode(run, image):
    records = [line.split("/") for line in run(["debugfs", "-R", "ls -p /", image]).splitlines()
               if line.startswith("/")]
    records = [record for record in records if len(record) >= 7 and record[5] == "boot_image.itb"]
    require(len(records) == 1, "Ambiguous debugfs root FIT entry")
    mode, uid, gid = int(records[0][2], 8), int(records[0][3]), int(records[0][4])
    require(stat.S_ISREG(mode) and uid >= 0 and gid >= 0, "Invalid original FIT inode metadata")
    return mode, uid, gid


def build_boot_copy(run, original, normal_fit, diagnostic_fit, work, boot_name=BOOT_NAME):
    copy = work / boot_name
    shutil.copyfile(original, copy)
    size = copy.stat().st_size
    run(["e2fsck", "-f", "-n", copy])
    before = work / "boot-before"
    after = work / "boot-after"
    before.mkdir()
    after.mkdir()
    run(["debugfs", "-R", "rdump / " + quote_debugfs(before), copy])
    embedded = before / "boot_image.itb"
    require(embedded.is_file() and not embedded.is_symlink(), "Expected regular /boot_image.itb")
    require(sha256(embedded) == sha256(normal_fit), "Boot filesystem FIT differs from input FIT")
    mode, uid, gid = fit_inode(run, copy)
    baseline = inventory(before)
    run(["debugfs", "-w", "-R", "rm /boot_image.itb", copy])
    run(["debugfs", "-w", "-R", "write " + quote_debugfs(diagnostic_fit) + " /boot_image.itb", copy])
    for field, value in (("mode", "0" + format(mode, "o")), ("uid", str(uid)), ("gid", str(gid))):
        run(["debugfs", "-w", "-R", f"set_inode_field /boot_image.itb {field} {value}", copy])
    run(["e2fsck", "-f", "-n", copy])
    require(fit_inode(run, copy) == (mode, uid, gid), "FIT mode/ownership preservation failed")
    require(copy.stat().st_size == size, "Diagnostic changed filesystem image size")
    run(["debugfs", "-R", "rdump / " + quote_debugfs(after), copy])
    updated = inventory(after)
    require(updated.get("boot_image.itb") == ("file", sha256(diagnostic_fit)),
            "debugfs did not install the diagnostic FIT")
    baseline.pop("boot_image.itb")
    updated.pop("boot_image.itb")
    require(updated == baseline, "Other boot filesystem paths or contents changed")
    return copy


def build(args, run=None):
    require(os.environ.get("CI") == "true", "Diagnostic artifact builder is CI-only")
    run = run or Commands()
    mode = getattr(args, "mode", "vgpu-observe")
    fit_name, boot_name = artifact_names(mode)
    inputs = {name: Path(getattr(args, name)).resolve() for name in
              ("normal_fit", "boot_image", "normal_dtb", "diagnostic_dtb", "its")}
    baseline = getattr(args, "baseline_dtb", None)
    if baseline is not None:
        inputs["baseline_dtb"] = Path(baseline).resolve()
    for path in inputs.values():
        require(path.is_file() and stat.S_ISREG(path.stat().st_mode), "Input must be a regular file")
    hashes = {name: sha256(path) for name, path in inputs.items()}
    output = Path(args.output_dir).resolve()
    require(not output.exists(), "Output directory must be new; defaults must never be overwritten")
    observer = validate_mode(mode, inputs["normal_dtb"], inputs["diagnostic_dtb"], inputs.get("baseline_dtb"))
    original_metadata = fit_metadata(run, inputs["normal_fit"])
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="tetris-vgpu-artifact-") as temporary:
        work = Path(temporary)
        payloads = extract_fit(run, inputs["normal_fit"], work / "normal")
        require(sha256(payloads[1]) == hashes["normal_dtb"], "Normal FIT DTB differs from supplied DTB")
        with payloads[0].open("rb") as stream:
            require(stream.read(2) == b"\x1f\x8b", "Kernel is not the declared gzip payload")
        source = work / "source"
        source.mkdir()
        shutil.copyfile(payloads[0], source / FILES[0])
        shutil.copyfile(inputs["diagnostic_dtb"], source / FILES[1])
        shutil.copyfile(payloads[2], source / FILES[2])
        shutil.copyfile(inputs["its"], source / "boot_image.its")
        diagnostic_fit = work / fit_name
        run(["mkimage", "-f", "boot_image.its", diagnostic_fit], cwd=source)
        require(fit_metadata(run, diagnostic_fit) == original_metadata, "FIT metadata/configuration changed")
        rebuilt = extract_fit(run, diagnostic_fit, work / "diagnostic")
        require(sha256(rebuilt[0]) == sha256(payloads[0]) and sha256(rebuilt[2]) == sha256(payloads[2]),
                "Diagnostic FIT changed immutable kernel/initramfs")
        require(sha256(rebuilt[1]) == hashes["diagnostic_dtb"], "Diagnostic FIT DTB mismatch")
        filesystem = ext_format(inputs["boot_image"])
        boot_copy = None
        if filesystem:
            boot_copy = build_boot_copy(run, inputs["boot_image"], inputs["normal_fit"], diagnostic_fit, work, boot_name)
        elif args.require_boot_image:
            raise ValueError("Unknown boot filesystem format; packaging gate required")
        require({name: sha256(path) for name, path in inputs.items()} == hashes, "An original input changed")
        shutil.copyfile(diagnostic_fit, output / fit_name)
        if boot_copy:
            shutil.copyfile(boot_copy, output / boot_name)
        artifacts = {path.name: {"sha256": sha256(path), "size": path.stat().st_size}
                     for path in output.iterdir()}
        manifest = {"diagnostic_only": True, "mode": mode, "observer": observer,
                    "dt_validation": "normal-to-OFF-to-active" if baseline else "normal-to-active",
                    "inputs": {name: {"path": str(path), "sha256": hashes[name]}
                               for name, path in inputs.items()},
                    "artifacts": artifacts, "boot_filesystem": filesystem,
                    "packaging_gate": None if boot_copy else "Unknown boot format: FIT only; do not flash as filesystem",
                    "immutable_kernel_sha256": sha256(payloads[0]),
                    "immutable_initramfs_sha256": sha256(payloads[2])}
        (output / "diagnostic-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (output / "SHA256SUMS").write_text("".join(
            f"{record['sha256']}  {name}\n" for name, record in sorted(artifacts.items())))
        if isinstance(run, Commands):
            (output / "diagnostic-tool-log.json").write_text(json.dumps(run.records, indent=2) + "\n")
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("normal-fit", "boot-image", "normal-dtb", "diagnostic-dtb", "its", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--require-boot-image", action="store_true")
    parser.add_argument("--mode", choices=MODES, default="vgpu-observe")
    parser.add_argument("--baseline-dtb", type=Path)
    args = parser.parse_args()
    existed = args.output_dir.exists()
    run = Commands()
    try:
        manifest = build(args, run)
    except Exception as error:
        if not existed and args.output_dir.is_dir():
            (args.output_dir / "diagnostic-failure.json").write_text(json.dumps(
                {"error": str(error), "commands": run.records}, indent=2) + "\n")
        raise
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
