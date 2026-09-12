#!/usr/bin/env python3
"""Compile actual U-Boot range predicate/map against synthetic boundary cases."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
source = (root / "arch/arm/lib/save_prev_bl_data.c").read_text()
start = source.index("static bool is_normal_memory_range(")
end = source.index("\nstatic int validate_mt6878_prev_bl_fdt(", start)
predicate = source[start:end]
board = (root / "arch/arm/mach-mediatek/mt6878/init.c").read_text()
start = board.index("static struct mm_region tetris_mem_map[]")
end = board.index("struct mm_region *mem_map = tetris_mem_map;", start)
mapping = board[start:end] + "struct mm_region *mem_map = tetris_mem_map;\n"
fixture = Path(__file__).with_name("prev-fdt-range-test.c").read_text()
assert fixture.count("/* INSERT_ACTUAL_SOURCE */") == 1
program = fixture.replace("/* INSERT_ACTUAL_SOURCE */", mapping + predicate)
with tempfile.TemporaryDirectory(prefix="tetris-fdt-range-") as temp:
    binary = str(Path(temp) / "test")
    subprocess.run([os.environ.get("HOSTCC", "cc"), "-std=c11", "-Wall", "-Wextra",
                    "-Werror", "-x", "c", "-", "-o", binary],
                   input=program, text=True, check=True)
    subprocess.run([binary], check=True)
