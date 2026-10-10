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
    "TETRIS_GPUEB_FLAT_ANALYSIS",
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
    "drivers/misc/gpueb-flat-analysis.o",
)
STRICT_PATCHES = frozenset((
    "0116-media-platform-mediatek-mt6878-seninf-phy-backend.patch",
    "0117-soc-mediatek-mt6878-ccci-first-start-backend.patch",
    "0118-pmdomain-mediatek-mt6878-gpueb-power-backend.patch",
    "0120-misc-tetris-gpueb-authenticated-ram-analysis.patch",
))
RESEARCH_DIR = "drivers/soc/mediatek/tetris-owner-smoke"
RESEARCH_SOURCES = {
    "patches/gpu/sram-owner/mt6878-gpueb-sram.c": f"{RESEARCH_DIR}/mt6878-gpueb-sram.c",
    "patches/gpu/sram-owner/mt6878-gpueb-sram.h": f"{RESEARCH_DIR}/mt6878-gpueb-sram.h",
    "patches/gpu/sram-owner/mt6878-gpueb-sram-core.c": f"{RESEARCH_DIR}/mt6878-gpueb-sram-core.c",
    "patches/gpu/sram-owner/mt6878-gpueb-sram-core.h": f"{RESEARCH_DIR}/mt6878-gpueb-sram-core.h",
    "patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c": f"{RESEARCH_DIR}/mt6878-gpueb-reset.c",
    "patches/gpu/reset-owner-draft/mt6878-gpueb-reset.h": f"{RESEARCH_DIR}/mt6878-gpueb-reset.h",
    "patches/gpu/reset-provider-draft/mt6878-gpueb-reset-provider.c": f"{RESEARCH_DIR}/mt6878-gpueb-reset-provider.c",
    "patches/gpu/reset-provider-draft/mt6878-gpueb-reset-provider.h": f"{RESEARCH_DIR}/mt6878-gpueb-reset-provider.h",
    "patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.c": f"{RESEARCH_DIR}/mt6878-gpueb-mfg0.c",
    "patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.h": f"{RESEARCH_DIR}/mt6878-gpueb-mfg0.h",
    "patches/gpu/bound-parent-draft/mt6878-gpueb-control.c": f"{RESEARCH_DIR}/mt6878-gpueb-control.c",
    "patches/gpu/bound-parent-draft/mt6878-gpueb-control.h": f"{RESEARCH_DIR}/mt6878-gpueb-control.h",
    "patches/modem/mt6878_md_startup_scope.c": f"{RESEARCH_DIR}/mt6878_md_startup_scope.c",
    "patches/modem/mt6878_md_startup_scope.h": "include/linux/soc/mediatek/mt6878_md_startup_scope.h",
    "patches/modem/mt6878_md_handoff_reservation.c": f"{RESEARCH_DIR}/mt6878_md_handoff_reservation.c",
    "patches/modem/mt6878_md_handoff_reservation.h": f"{RESEARCH_DIR}/mt6878_md_handoff_reservation.h",
    "patches/modem/mt6878_md_pss32.c": f"{RESEARCH_DIR}/mt6878_md_pss32.c",
    "patches/modem/mt6878_md_pss32.h": f"{RESEARCH_DIR}/mt6878_md_pss32.h",
    "patches/camera-smi-owner/mt6878-smi-camera-reset.inc": "drivers/memory/mt6878-smi-camera-reset.inc",
    "patches/camera-smi-owner/smi-camera-reset.h": "include/soc/mediatek/smi-camera-reset.h",
}
PROVIDER_PATCH = "patches/camera-smi-owner/provider.patch"
# Use the existing provider Kbuild, never replace drivers/memory/Makefile.
PROVIDER_OBJECTS = ("drivers/memory/mtk-smi.o",)
RESEARCH_OBJECTS = tuple(f"{RESEARCH_DIR}/{name}.o" for name in (
    "mt6878-gpueb-sram", "mt6878-gpueb-sram-core",
    "mt6878-gpueb-reset", "mt6878-gpueb-reset-provider",
    "mt6878-gpueb-mfg0", "mt6878-gpueb-control",
    "mt6878_md_startup_scope", "mt6878_md_handoff_reservation",
    "mt6878_md_pss32",
))
CAMERA_MANIFEST = "patches/camera-pipeline-owner/STAGING.json"
CAMERA_GRAPH = "drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.c"
CAMERA_REVIEW_PATCHES = (
    "patches/camera-seninf-controller/imx882-native-streams.patch",
    "patches/camera-seninf-controller/native-bind.patch",
    "patches/camera-native-capture/native-pm.patch",
    "patches/camera-joint-reset/video-cold.patch",
)


def camera_staging(root, manifest=CAMERA_MANIFEST):
    data = json.loads((root / manifest).read_text())
    destination = data["destination"]
    if destination != "drivers/media/platform/mediatek/tetris-camera-owner-smoke":
        raise ValueError("unexpected camera staging destination")
    sources = data["sources"]
    if not isinstance(sources, list) or not sources or len(set(sources)) != len(sources):
        raise ValueError("invalid camera source list")
    mapping = {}
    for source in sources:
        path = Path(source)
        if (not source.startswith("patches/camera-") or ".." in path.parts
                or path.suffix not in (".c", ".h", ".inc")):
            raise ValueError("unsafe camera source path")
        target = f"{destination}/{path.name}"
        if target in mapping.values():
            raise ValueError("camera basename collision")
        mapping[source] = target
    names = [*data["objects"]]
    if "fault_object" in data:
        names.append(data["fault_object"])
    if len(set(names)) != len(names):
        raise ValueError("duplicate camera object")
    for name in names:
        if Path(name).name != name or not name.endswith(".o"):
            raise ValueError("unsafe camera object path")
        if f"{destination}/{Path(name).with_suffix('.c')}" not in mapping.values():
            raise ValueError("camera object lacks production source")
    symbols = [*data.get("required_enabled", []), *data.get("fault_required_enabled", [])]
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in symbols):
        raise ValueError("invalid camera config symbol")
    return mapping, tuple(f"{destination}/{name}" for name in names), tuple(symbols)


CAMERA_SOURCES, CAMERA_OBJECTS, CAMERA_ENABLE = camera_staging(Path(__file__).resolve().parents[1])
# Hidden vb2 helpers need an upstream selector in the isolated config. The
# virtual driver is neither compiled nor installed by this object-only harness.
CAMERA_SELECTORS = ("MEDIA_TEST_SUPPORT", "V4L_TEST_DRIVERS", "VIDEO_VIVID")
RESEARCH_SOURCES.update(CAMERA_SOURCES)
RESEARCH_OBJECTS += CAMERA_OBJECTS
CAMERA_JOINT_MANIFEST = "patches/camera-joint-reset/STAGING.json"
CAMERA_JOINT_SOURCES, CAMERA_JOINT_OBJECTS, _ = camera_staging(
    Path(__file__).resolve().parents[1], CAMERA_JOINT_MANIFEST)
if set(CAMERA_JOINT_SOURCES.values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate camera joint-reset staging destination")
RESEARCH_SOURCES.update(CAMERA_JOINT_SOURCES)
RESEARCH_OBJECTS += CAMERA_JOINT_OBJECTS
CAMERA_REPEAT_MANIFEST = "patches/camera-repeat-capture/STAGING.json"
CAMERA_REPEAT_CHECK = "patches/camera-repeat-capture/check.py"
CAMERA_REPEAT_SOURCES, CAMERA_REPEAT_OBJECTS, _ = camera_staging(
    Path(__file__).resolve().parents[1], CAMERA_REPEAT_MANIFEST)
if set(CAMERA_REPEAT_SOURCES.values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate repeat-capture staging destination")
RESEARCH_SOURCES.update(CAMERA_REPEAT_SOURCES)
RESEARCH_OBJECTS += CAMERA_REPEAT_OBJECTS
CAMERA_REPEAT_PATCHES = tuple("patches/camera-repeat-capture/" + name for name in (
    "epoch-owner.patch", "epoch-stop-lock.patch", "epoch-final-retire.patch", "epoch-video.patch"))
CAM_MAIN_MANIFEST = "patches/camera-cam-main-provider/STAGING.json"
CAM_MAIN_CHECK = "patches/camera-cam-main-provider/check-staging.py"
CAM_MAIN_PLAN = json.loads((Path(__file__).resolve().parents[1] / CAM_MAIN_MANIFEST).read_text())
if (set(CAM_MAIN_PLAN["sources"].values()) & set(RESEARCH_SOURCES.values()) or
        any(Path(name).is_absolute() or ".." in Path(name).parts
            for name in (*CAM_MAIN_PLAN["sources"], *CAM_MAIN_PLAN["sources"].values()))):
    raise ValueError("unsafe or duplicate CAM_MAIN staging input")
RESEARCH_SOURCES.update(CAM_MAIN_PLAN["sources"])
RESEARCH_OBJECTS += tuple(CAM_MAIN_PLAN["research_objects"])
PROVIDER_OBJECTS += tuple(CAM_MAIN_PLAN["provider_objects"])
CAM_MAIN_ENABLE = tuple(CAM_MAIN_PLAN["required_enabled"])
CAM_MAIN_REACHABLE = tuple(CAM_MAIN_PLAN["required_reachable"])


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


def stage_research_sources(kernel, root=Path(".")):
    directories = {str(Path(name).parent) for name in RESEARCH_OBJECTS}
    destinations = [*RESEARCH_SOURCES.values(), *(f"{name}/Makefile" for name in directories)]
    for destination in destinations:
        if (kernel / destination).exists():
            raise ValueError(f"research destination already exists: {destination}")
    for source in RESEARCH_SOURCES:
        if not (root / source).is_file():
            raise ValueError(f"research source is missing: {source}")
    for source, destination in RESEARCH_SOURCES.items():
        target = kernel / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, target)
    for directory in sorted(directories):
        names = [Path(name).name for name in RESEARCH_OBJECTS if str(Path(name).parent) == directory]
        (kernel / directory / "Makefile").write_text("obj-y += " + " ".join(names) + "\n")


def stage_camera_overlays(kernel, root=Path(".")):
    destination = kernel / Path(next(iter(CAMERA_SOURCES.values()))).parent
    graph = kernel / CAMERA_GRAPH
    staged = destination / graph.name
    if not graph.is_file() or staged.exists():
        raise ValueError("camera overlay requires unique packaged graph source")
    # Basename overlays share the isolated closure; keep the graph's production
    # Kbuild target, never introduce a duplicate object or replace parent Kbuild.
    shutil.copyfile(graph, staged)
    try:
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", (root / CAMERA_REVIEW_PATCHES[0]).resolve()])
        for name in CAMERA_REVIEW_PATCHES[1:]:
            run(["patch", "--batch", "--fuzz=0", "-p1", "-d", destination,
                 "-i", (root / name).resolve()])
        shutil.copyfile(staged, graph)
    finally:
        staged.unlink()


def stage_camera_repeat(kernel, root=Path(".")):
    destination = kernel / Path(next(iter(CAMERA_SOURCES.values()))).parent
    for name in CAMERA_REPEAT_PATCHES:
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", destination,
             "-i", (root / name).resolve()])


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


def config_options(kernel, output, research_owners):
    options = [kernel / "scripts/config", "--file", output / ".config"]
    enabled = ENABLE + (CAMERA_SELECTORS + CAMERA_ENABLE + CAM_MAIN_ENABLE +
                        CAM_MAIN_REACHABLE if research_owners else ())
    for symbol in dict.fromkeys(enabled):
        options.extend(["-e", symbol])
    for symbol in MODULES:
        options.extend(["-m", symbol])
    return options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--research-owners", action="store_true",
                        help="also compile frozen default-off owners without shipping wiring")
    parser.add_argument("--work", type=Path, default=Path("/tmp/tetris-kernel-smoke"))
    args = parser.parse_args()
    package = PACKAGE.resolve()
    manifest = plan(package)
    objects = OBJECTS
    if args.research_owners:
        objects += RESEARCH_OBJECTS + PROVIDER_OBJECTS
        manifest["objects"] = objects
        manifest["research_source_sha256"] = {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in RESEARCH_SOURCES
        }
        manifest["research_source_sha256"][CAMERA_MANIFEST] = hashlib.sha256(
            Path(CAMERA_MANIFEST).read_bytes()).hexdigest()
        manifest["research_source_sha256"][CAMERA_JOINT_MANIFEST] = hashlib.sha256(
            Path(CAMERA_JOINT_MANIFEST).read_bytes()).hexdigest()
        joint_check = "patches/camera-joint-reset/check.py"
        manifest["research_source_sha256"][joint_check] = hashlib.sha256(
            Path(joint_check).read_bytes()).hexdigest()
        manifest["research_source_sha256"][PROVIDER_PATCH] = hashlib.sha256(
            Path(PROVIDER_PATCH).read_bytes()).hexdigest()
        for name in CAMERA_REVIEW_PATCHES:
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (CAMERA_REPEAT_MANIFEST, CAMERA_REPEAT_CHECK,
                     "patches/camera-repeat-capture/test-completion-order.py",
                     "patches/camera-repeat-capture/generate-overlays.py", *CAMERA_REPEAT_PATCHES):
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (CAM_MAIN_MANIFEST, CAM_MAIN_CHECK, CAM_MAIN_PLAN["overlay"]):
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
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
    if args.research_owners:
        # Built-in translation units: no MODULE define, probe, parent Kbuild
        # linkage or shipping Kconfig change. Preserve exact production bytes.
        stage_research_sources(kernel)
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", Path(PROVIDER_PATCH).resolve()])
        stage_camera_overlays(kernel)
        run(["python3", "patches/camera-joint-reset/check.py",
             "--staged-only", "--kernel-tree", kernel])
        # Verify the cold chain first; the repeat worker delegates to that chain.
        run(["python3", CAMERA_REPEAT_CHECK])
        stage_camera_repeat(kernel)
        manifest["derived_camera_sources_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in (*CAMERA_SOURCES.values(), *CAMERA_JOINT_SOURCES.values(),
                                *CAMERA_REPEAT_SOURCES.values())
        }
        run(["python3", CAM_MAIN_CHECK, "--kernel-tree", kernel])
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", Path(CAM_MAIN_PLAN["overlay"]).resolve()])
        run(["python3", CAM_MAIN_CHECK, "--staged-tree", kernel])
        manifest["derived_camera_graph_sha256"] = hashlib.sha256((kernel / CAMERA_GRAPH).read_bytes()).hexdigest()
    output = args.work / "objects"
    output.mkdir()
    shutil.copyfile(package / CONFIG, output / ".config")
    run(config_options(kernel, output, args.research_owners))
    make = ["make", "-C", kernel, f"O={output}", "ARCH=arm64", "LLVM=1", "-j4"]
    if args.research_owners:
        camera_dir = Path(next(iter(CAMERA_SOURCES.values()))).parent
        make.append(f"KCFLAGS=-I{kernel / camera_dir}")
    run([*make, "olddefconfig"])
    shutil.copyfile(output / ".config", report / "isolated.config")
    config = (output / ".config").read_text().splitlines()
    for symbol in MODULES:
        if f"CONFIG_{symbol}=m" not in config:
            raise ValueError(f"isolated dependency missing: {symbol}")
    if args.research_owners:
        for symbol in CAMERA_ENABLE:
            if f"CONFIG_{symbol}=y" not in config:
                raise ValueError(f"isolated camera dependency missing: {symbol}")
        for symbol in CAM_MAIN_REACHABLE:
            if not any(f"CONFIG_{symbol}={value}" in config for value in ("y", "m")):
                raise ValueError(f"isolated CAM_MAIN dependency missing: {symbol}")
    run([*make, "-k", *objects])
    identities = {}
    for name in objects:
        target = output / name
        if not target.is_file() or not target.stat().st_size:
            raise ValueError(f"missing object: {name}")
        identities[name] = object_identity(target)
        identities[name]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(name + ": " + json.dumps(identities[name]), flush=True)
    if list(output.rglob("*.ko")) or (output / "vmlinux").exists():
        raise ValueError("object-only CI must not produce runtime modules or kernel")
    if args.research_owners:
        # Also compile the real video and clock owners without private KUnit cases.
        # No fixture execution or change to the shipping kernel configuration.
        video_objects = tuple(name for name in CAMERA_OBJECTS
                              if Path(name).name in ("mt6878-native-video.o", "video-smoke.o"))
        if len(video_objects) != 2:
            raise ValueError("video variant requires both explicit objects")
        cam_main_objects = tuple(CAM_MAIN_PLAN["provider_objects"] + CAM_MAIN_PLAN["research_objects"])
        repeat_consumers = tuple(name for name in CAMERA_OBJECTS
                                 if Path(name).name in ("mt6878-native-capture.o", "mt6878-camsv-platform.o"))
        if len(repeat_consumers) != 2:
            raise ValueError("repeat-capture variant requires both actual consumers")
        variant_objects = (video_objects + cam_main_objects + CAMERA_JOINT_OBJECTS +
                           CAMERA_REPEAT_OBJECTS + repeat_consumers)
        run([kernel / "scripts/config", "--file", output / ".config", "-d", "KUNIT"])
        run([*make, "olddefconfig"])
        if any(line.startswith("CONFIG_KUNIT=")
               for line in (output / ".config").read_text().splitlines()):
            raise ValueError("video KUnit-disabled configuration did not resolve")
        shutil.copyfile(output / ".config", report / "video-kunit-disabled.config")
        for name in variant_objects:
            (output / name).unlink()
        run([*make, *variant_objects])
        manifest["video_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in video_objects
        }
        manifest["cam_main_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in cam_main_objects
        }
        manifest["camera_joint_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in CAMERA_JOINT_OBJECTS
        }
        manifest["camera_repeat_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in (*CAMERA_REPEAT_OBJECTS, *repeat_consumers)
        }
    manifest["status"] = "passed"
    manifest["object_identities"] = identities
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
