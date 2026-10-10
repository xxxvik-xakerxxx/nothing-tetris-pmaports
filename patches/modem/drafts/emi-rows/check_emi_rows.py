#!/usr/bin/env python3
"""Local static checks; producer/transport C and actual LK instructions CI-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "bffec9306e7c40a432d79deefb450230c2ee2360"
LK_SHA = "29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f"


def static_check():
    build = (HERE / "tetris_modem_emi_rows.c").read_text()
    program = (HERE / "tetris_modem_emi_rows_program.c").read_text()
    assert "padding(&result.memory)" in build
    assert "if (used_preset++)" in build
    assert "(b->attributes & 0x18) == 8 && b->size > biggest" in build
    assert "(resources->nc.base | resources->cache.base) & 0x1ffffffULL" in build
    assert "intersect(resources->firmware.base, layout.memory_size" not in build
    assert build.count("intersect(resources->firmware.base, resources->firmware.capacity") == 2
    fixture = (HERE / "test_emi_rows.c").read_text()
    assert "memset(rom + rom_size - 512 + 0x180, 0, 4)" in fixture
    assert "ops->smc(ops->context, 0xc2000415U, 6, 40, r->role, 0" in program
    assert "tx->padding.words[j + 3] & ~r->policy[j]" in program
    assert "tetris_modem_program_emi_range" in program
    assert "tx->error ? tx->error : -EALREADY" in program
    for forbidden in ("arm_smccc_smc", "writel", "lmb_free", "fdt_setprop"):
        assert forbidden not in build
    print("PASS: static producer/preset/one-attempt/no-RAM-free checks; NOT C compilation")


def compare_lk(lk, plan):
    if os.environ.get("CI") != "true":
        raise SystemExit("LK instruction execution is CI-only")
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    from unicorn.arm64_const import (
        UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
    )
    raw = lk.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LK_SHA:
        raise ValueError("unknown LK; do not reuse these offsets")
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    machine.mem_map(0, 0x1c0000)
    machine.mem_write(0, raw[512:512 + 0x1c0000])
    stack, data, stop = 0x70000000, 0x71000000, 0x72000000
    machine.mem_map(stack, 0x10000)
    machine.mem_map(data, 0x1000)
    machine.mem_map(stop, 0x1000)
    machine.mem_write(data, b"".join(struct.pack("<IIIIQ", *b) for b in plan["initial"]))
    # BSS state starts with no consumed preset-list entry; this is synthetic RAM.
    machine.mem_write(0x1b6188, bytes(8))

    def code(uc, address, size, context):
        if address in (0x69c28, 0x25d98, 0x26d1c):
            # Logging/dump only, not a map mutation or protection operation.
            uc.reg_write(UC_ARM64_REG_X0, 0)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
            return
        assert (0x270e8 <= address < 0x277f8 or
                0x81918 <= address < 0x81c74), hex(address)

    def write(uc, access, address, size, value, context):
        assert (stack <= address and address + size <= stack + 0x10000 or
                data <= address and address + size <= data + 0x1000 or
                0x198678 <= address and address + size <= 0x198798 or
                0x1b6168 <= address and address + size <= 0x1b6190), hex(address)

    machine.hook_add(UC_HOOK_CODE, code)
    machine.hook_add(UC_HOOK_MEM_WRITE, write)
    machine.reg_write(UC_ARM64_REG_X0, data)
    machine.reg_write(UC_ARM64_REG_X1, len(plan["initial"]))
    machine.reg_write(UC_ARM64_REG_SP, stack + 0x8000)
    machine.reg_write(UC_ARM64_REG_LR, stop)
    machine.emu_start(0x27108, stop, count=100000)
    assert machine.reg_read(UC_ARM64_REG_PC) == stop, "bounded LK walker did not return"
    memory = [list(struct.unpack("<IIIIQ", machine.mem_read(data + i * 24, 24)))
              for i in range(len(plan["initial"]))]
    assert memory == plan["memory"], "actual LK padding-selection flags differ"
    for i in range(9):
        base, size, flags, role, slot = struct.unpack(
            "<QIIII", machine.mem_read(0x198678 + i * 24, 24))
        kind = 0 if not flags & 1 else 2 if flags & 2 else 1
        ours = plan["rows"][i]
        assert kind == ours[0], (slot, flags, ours)
        if kind:
            assert [kind, role, slot, base, size] == ours, (slot, ours, base, size)
    print("PASS: actual pinned LK padding/region/DSP/window/preset-list code vs actual C producer")
    print("Synthetic RAM only; no SMC, allocator, power or handset instructions executed")


def native_ci(uboot, stock, lk):
    if os.environ.get("CI") != "true":
        raise SystemExit("C build/execution is CI-only")
    # Reuse the already-reviewed boot-stage host-header policy, not production code.
    with tempfile.TemporaryDirectory(prefix="tetris-emi-rows-") as directory:
        root = Path(directory)
        for name in ("tetris_modem_layout.c", "tetris_modem_layout.h",
                     "tetris_modem_emi.c", "tetris_modem_emi.h"):
            data = subprocess.check_output([
                "git", "-C", str(uboot), "show",
                f"{PIN}:board/mediatek/mt6878/{name}"])
            (root / name).write_bytes(data)
        for name in ("tetris_modem_emi_rows.c", "tetris_modem_emi_rows.h",
                     "tetris_modem_emi_rows_program.c", "test_emi_rows.c"):
            (root / name).write_bytes((HERE / name).read_bytes())
        headers = {
            "linux/errno.h": "#include <asm-generic/errno.h>\n",
            "linux/string.h": "#include <string.h>\n",
            "linux/arm-smccc.h": (
                "#ifndef TEST_SMCCC_H\n#define TEST_SMCCC_H\n"
                "struct arm_smccc_res { unsigned long a0, a1, a2, a3; };\n"
                "void test_smc(unsigned long, unsigned long, unsigned long, "
                "unsigned long, unsigned long, unsigned long, unsigned long, "
                "unsigned long, struct arm_smccc_res *);\n"
                "#define arm_smccc_smc test_smc\n#endif\n"),
        }
        for name, text in headers.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        binary = root / "test-rows"
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
            "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(root),
            *(str(root / name) for name in (
                "tetris_modem_layout.c", "tetris_modem_emi.c", "tetris_modem_emi_rows.c",
                "tetris_modem_emi_rows_program.c", "test_emi_rows.c")),
            "-o", str(binary),
        ], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        for case in (*range(18), 19, 20):
            subprocess.run([str(binary), str(stock), str(case)], check=True, env=env)
        print("PASS: 20 actual public-footer producer/SIP adapter sanitizer cases")
        if lk:
            plan = json.loads(subprocess.check_output(
                [str(binary), str(stock), "18"], env=env))
            compare_lk(lk, plan)
        print("Firmware authentication must separately pass main's frozen signed-input oracle")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--uboot", type=Path)
    parser.add_argument("--stock-container", type=Path)
    parser.add_argument("--lk", type=Path)
    args = parser.parse_args()
    static_check()
    if args.native_ci:
        if not args.uboot or not args.stock_container:
            parser.error("native CI needs pinned --uboot and real --stock-container")
        native_ci(args.uboot, args.stock_container, args.lk)


if __name__ == "__main__":
    main()
