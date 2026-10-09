#!/usr/bin/env python3
"""Apply package patches to disposable source files; never compile or use hardware."""

import argparse
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("kernel-object-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def paths(package, patches):
    result = set()
    created = set()
    for patch in patches:
        text = (package / patch).read_text(encoding="latin-1")
        created.update(re.findall(r"^--- [^\n]+\n\+\+\+ [^/\s]+/(\S+)[^\n]*\n@@ -0,0 ", text, re.M))
        for name in re.findall(r"^--- [^/\s]+/(\S+)", text, re.M):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unsafe source path")
            if name not in created:
                result.add(name)
        created.update(re.findall(r"^--- /dev/null\n\+\+\+ [^/\s]+/(\S+)", text, re.M))
    return sorted(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, nargs="?")
    parser.add_argument("--list-paths", action="store_true")
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[1] / smoke.PACKAGE
    plan = smoke.plan(package)
    source_paths = paths(package, plan["patches"])
    if args.list_paths:
        print("\n".join("/" + name for name in source_paths))
        return
    if not args.kernel:
        parser.error("pristine pinned kernel tree required")
    with tempfile.TemporaryDirectory(prefix="tetris-patch-stack-") as temp:
        root = Path(temp)
        for name in source_paths:
            source = args.kernel / name
            if not source.is_file():
                raise ValueError(f"pristine source is missing: {name}")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for name in plan["patches"]:
            flags = ["--fuzz=0"] if name in smoke.STRICT_PATCHES else []
            result = subprocess.run(["patch", "--batch", *flags, "-p1", "-i", str(package / name)],
                                    cwd=root, capture_output=True, text=True)
            if result.returncode:
                print(result.stdout + result.stderr)
                for reject in root.rglob("*.rej"):
                    print(f"REJECT {reject.relative_to(root)}:\n{reject.read_text()}")
                    source = reject.with_suffix("")
                    if source.name == "mt6878-nothing-tetris.dts":
                        text = source.read_text()
                        print("CURRENT PINCTRL:\n" + text.split("&pio {", 1)[1][:1800])
                raise SystemExit(f"package stack failed: {name}")
        native = root / "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dts"
        if not native.is_file():
            raise ValueError("native display DT missing from final stack")
        base = root / "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris.dts"
        if re.search(r"gps_l[15]_lna|PINMUX_GPIO14[34]", base.read_text()):
            raise ValueError("unproven GNSS LNA wiring survived final stack")
        print(f"PASS: {len(plan['patches'])} packaged kernel patches; final DT source has no unproven LNA pins")


if __name__ == "__main__":
    main()
