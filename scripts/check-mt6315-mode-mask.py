#!/usr/bin/env python3
"""Check actual regulator phase selection; native compilation is CI-only."""
import argparse
from pathlib import Path
import subprocess
import tempfile

from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("readback", HERE / "check-panthor-vgpu-readback.py")
readback = module_from_spec(spec)
spec.loader.exec_module(readback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--apply-only", action="store_true")
    args = parser.parse_args()
    package = HERE.parent / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
    driver = "drivers/regulator/mt6315-regulator.c"
    binding = "Documentation/devicetree/bindings/regulator/mt6315-regulator.yaml"
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name in (driver, binding):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(readback.file_text(args.kernel, readback.KERNEL_COMMIT, name))
        for name in ("0105-regulator-mt6315-read-active-voltage-selector.patch",
                     "0108-regulator-mt6315-board-mode-mask.patch"):
            subprocess.run(["git", "apply", "--check", str(package / name)],
                           cwd=root, check=True)
            subprocess.run(["git", "apply", str(package / name)], cwd=root, check=True)
        source = (root / driver).read_text()
        readback.require("ret = mt6315_init_mode_masks(dev, pdev->usid, init_data);" in source,
                         "probe does not select mode masks")
        helper = readback.function(source, "static int mt6315_init_mode_masks(")
        if args.apply_only:
            print("PASS: GPU/camera PMIC patch applies after active-selector patch; no build")
            return
        generated = root / "mode-mask-source.h"
        generated.write_text(helper)
        binary = root / "test"
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(root),
                   str(HERE / "tests/mt6315-mode-mask.c"), "-o", str(binary)]
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)
        for old, new in (("= mask;", "= 11;"),
                         ("return ret;", "return 0;"),
                         ("mask & ~GENMASK(MT6315_VBUCK_MAX - 1, 0)", "0")):
            readback.require(old in helper, "missing mutation anchor")
            generated.write_text(helper.replace(old, new))
            subprocess.run(command, check=True)
            result = subprocess.run([str(binary)], cwd=root, capture_output=True)
            readback.require(result.returncode != 0, "accepted broken phase-mask implementation")
        print("PASS: wrong phase mask, swallowed error and invalid high-bit mutants rejected")


if __name__ == "__main__":
    main()
