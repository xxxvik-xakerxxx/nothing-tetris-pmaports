#!/usr/bin/env python3
"""Read-only additive staging/overlay checks; never stage, compile or activate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def safe_path(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError(f"unsafe staging path: {value}")
    return path


def overlay_text(base, overlay):
    lines = overlay.splitlines()
    hunks = [i for i, line in enumerate(lines) if line.startswith("@@ ")]
    if len(hunks) != 1:
        raise ValueError("expected exactly one provider overlay hunk")
    header = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", lines[hunks[0]])
    if not header:
        raise ValueError("invalid provider hunk header")
    body = lines[hunks[0] + 1:]
    old = "\n".join(line[1:] for line in body if line.startswith((" ", "-"))) + "\n"
    new = "\n".join(line[1:] for line in body if line.startswith((" ", "+"))) + "\n"
    if base.count(old) != 1:
        raise ValueError("provider overlay context is absent/ambiguous")
    offset = base[:base.index(old)].count("\n") + 1
    if int(header[1]) != offset or int(header[3]) != offset:
        raise ValueError("provider hunk line numbers drifted from shipped base")
    if int(header[2]) != old.count("\n") or int(header[4]) != new.count("\n"):
        raise ValueError("provider hunk line counts are incorrect")
    trailing = 0
    for line in reversed(body):
        if not line.startswith(" "):
            break
        trailing += 1
    if trailing < 3 and not base.endswith(old):
        raise ValueError("non-EOF hunk needs three trailing context lines for GNU patch")
    return base.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path,
                        help="before overlay: validate actual provider and dry-run patch")
    parser.add_argument("--staged-tree", type=Path,
                        help="after overlay: validate exact additive copies and target")
    parser.add_argument("--plan", action="store_true", help="emit JSON for parent harness")
    args = parser.parse_args()
    manifest = json.loads((HERE / "STAGING.json").read_text())
    sources = manifest["sources"]
    if len(set(sources.values())) != len(sources):
        raise ValueError("duplicate destination")
    for source, destination in sources.items():
        if not (ROOT / safe_path(source)).is_file():
            raise ValueError(f"missing source: {source}")
        safe_path(destination)
    if manifest["config_variants"] != [{"KUNIT": "y"}, {"KUNIT": "n"}]:
        raise ValueError("both provider fixture configurations are mandatory")
    for name in manifest["research_objects"]:
        if str(safe_path(name).with_suffix(".c")) not in sources.values():
            raise ValueError(f"object without staged source: {name}")
    package = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
    packaged = (package / manifest["requires_packaged_patch"]).read_text()
    target = manifest["overlay_target"]
    safe_path(target)
    section = packaged.split(f"+++ b/{target}\n", 1)[1]
    base = "\n".join(line[1:] for line in section.splitlines()
                     if line.startswith("+") and not line.startswith("+++")) + "\n"
    overlay = ROOT / safe_path(manifest["overlay"])
    expected = overlay_text(base, overlay.read_text())
    # Keep checks independent of any mutable production clock/driver state.
    tests = (HERE / "cam-main-lease-test.inc").read_text()
    if re.search(r"clk_mt6878_cam_drv\s*[.=]|platform_driver_register\s*\(", tests):
        raise ValueError("fixture mutates/registers the actual provider")
    if "struct cam_main_lock_race race =" not in tests:
        raise ValueError("contention fixture must use invocation-local state")
    run = subprocess.run([sys.executable, str(HERE / "check.py")],
                         check=True, capture_output=True, text=True)
    if args.kernel_tree:
        tree = args.kernel_tree.resolve()
        if (tree / target).read_text() != base:
            raise ValueError("actual provider differs from packaged 0092 base")
        command = ["patch", "--dry-run", "--batch", "--forward", "--fuzz=0", "-p1"]
        result = subprocess.run(command, cwd=tree, input=overlay.read_text(),
                                text=True, capture_output=True)
        if result.returncode:
            version = subprocess.run(["patch", "--version"], text=True,
                                     capture_output=True)
            raise RuntimeError(
                f"CAM_MAIN overlay dry-run failed: rc={result.returncode}, tree={tree}, "
                f"base_sha256={hashlib.sha256(base.encode()).hexdigest()}\n"
                f"command: {' '.join(command)}\n"
                f"patch version: {version.stdout.strip()} {version.stderr.strip()}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    if args.staged_tree:
        tree = args.staged_tree.resolve()
        if (tree / target).read_text() != expected:
            raise ValueError("staged provider overlay mismatch")
        for source, destination in sources.items():
            if (tree / destination).read_bytes() != (ROOT / source).read_bytes():
                raise ValueError(f"staged input mismatch: {destination}")
    if args.plan:
        manifest["base_sha256"] = hashlib.sha256(base.encode()).hexdigest()
        manifest["overlaid_sha256"] = hashlib.sha256(expected.encode()).hexdigest()
        manifest["source_sha256"] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
        }
        print(json.dumps(manifest, indent=2))
    else:
        print(run.stdout.strip())
        print("CAM_MAIN additive staging/fixture/overlay guards PASS; no C/KUnit execution")


if __name__ == "__main__":
    main()
