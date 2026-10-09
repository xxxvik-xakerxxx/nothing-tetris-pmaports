#!/usr/bin/env python3
"""Extract actual patched driver helpers for CI-native, no-I/O unit tests."""
from pathlib import Path
import sys
import subprocess
import os

from test_supply_inventory import SupplyInventory, patch


def definition(source, start):
    offset = source.index(start)
    opening = source.index("{", offset)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    if source[end:end + 1] == ";":
        end += 1
    return source[offset:end] + "\n"


def main():
    SupplyInventory.setUpClass()
    try:
        check = SupplyInventory("test_partial_provider_cannot_write_unowned_phases")
        check.test_partial_provider_cannot_write_unowned_phases()
        observer = os.environ.get("TETRIS_GPU_OBSERVER_TESTS", "0") == "1"
        if observer:
            name = "0114-regulator-mt6315-read-only-vgpu-observer.patch"
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=SupplyInventory.tree, input=patch(name),
                                    text=True, capture_output=True)
            if result.returncode:
                raise AssertionError(f"{name}:\n{result.stdout}{result.stderr}")
        source = (SupplyInventory.tree / "drivers/regulator/mt6315-regulator.c").read_text()
        names = [
            "struct mt_regulator_init_data {",
            "static int mt6315_described_rails(",
            "static int mt6315_init_mode_masks(",
            "static bool mt6315_mode_mask_owned(",
        ]
        if observer:
            names += [
            "struct mt6315_vgpu_snapshot {",
            "static bool mt6315_vgpu_readable_reg(",
            "static bool mt6315_vgpu_writeable_reg(",
            "static int mt6315_read_vgpu(",
            ]
        definitions = [definition(source, name) for name in names]
        Path(sys.argv[1]).write_text("\n".join(definitions))
    finally:
        SupplyInventory.tmp.cleanup()


if __name__ == "__main__":
    main()
