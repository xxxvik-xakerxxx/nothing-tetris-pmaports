#!/usr/bin/env python3
"""Pinned source ABI oracle; no execution, devices or network, no C build."""
import hashlib
import re
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM


def check(path):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83")
    with path.open("rb") as handle:
        elf = ELFFile(handle)
        segments = [(s["p_vaddr"], s.data()) for s in elf.iter_segments()
                    if s["p_type"] == "PT_LOAD"]
        symbols = elf.get_section_by_name(".dynsym")
        reloc = elf.get_section_by_name(".rela.plt")
        plt = elf.get_section_by_name(".plt")["sh_addr"]
        entries = {plt + 32 + i * 16:
                   symbols.get_symbol(r["r_info_sym"]).name
                   for i, r in enumerate(reloc.iter_relocations())}
    def read(addr, size):
        for start, data in segments:
            if start <= addr and addr + size <= start + len(data):
                return data[addr - start:addr - start + size]
        raise AssertionError(hex(addr))
    assert read(0x227b8, 15) == b"/dev/ttyCMIPC5\0"
    assert read(0x1a5a1, 5) == b"gnss\0"
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    def operands(text):
        return re.sub(r"#(0x[0-9a-f]+|[0-9]+)",
                      lambda match: "#" + str(int(match[1], 0)), text)
    def instruction(addr):
        i = next(md.disasm(read(addr, 4), addr))
        # Capstone 4 prints MOVZ, newer releases print its unshifted MOV alias.
        # Keep exact operands/addresses and the whole-file SHA requirement.
        mnemonic = "mov" if i.mnemonic == "movz" and "lsl" not in i.op_str else i.mnemonic
        return mnemonic, operands(i.op_str)
    expected = {
        0x7f4c8: ("mov", "w0, #0x2710"),
        0x7f4a8: ("add", "x0, x0, #0x7b8"),
        0x7f4ec: ("add", "x0, x0, #0x5a1"),
        0x7f4f4: ("cbz", "w0, #0x7f520"),
        0x7f548: ("mov", "w0, #0x8d"),
        0x7f54c: ("mov", "w1, #1"),
        0x7f570: ("mov", "w0, #0x1388"),
        0x7f618: ("mov", "x0, x20"),
        0x7f61c: ("mov", "w1, wzr"),
        0x7f620: ("mov", "x2, xzr"),
        0x7f63c: ("ldr", "w4, [x0]"),
        0x7f640: ("cbnz", "w4, #0x7f684"),
        0x7f64c: ("adr", "x21, #0xde490"),
        0x7f658: ("mov", "w1, #0x101"),
        0x7f65c: ("mov", "x2, xzr"),
        0x7f678: ("ldr", "w8, [x0]"),
        0x7f67c: ("b", "#0x7f6e8"),
        0x7f6ec: ("str", "w8, [x21]"),
        0x7f6f8: ("mov", "w1, #0x102"),
        0x7f6fc: ("mov", "x2, xzr"),
        0x7f718: ("ldr", "w8, [x0]"),
        0x7f734: ("str", "w8, [x21, #4]"),
        0x7f740: ("mov", "w1, #0x103"),
        0x7f744: ("mov", "x2, xzr"),
        0x7f760: ("ldr", "w8, [x0]"),
        0x7f774: ("adr", "x20, #0xde4a0"),
        0x7f794: ("str", "w8, [x20]"),
    }
    for addr, value in expected.items():
        normalized = value[0], operands(value[1])
        assert instruction(addr) == normalized, (hex(addr), instruction(addr), value)
    for addr, name in {
        0x7f4ac: "SETCOM", 0x7f4cc: "mipc_msg_set_timeout_once",
        0x7f4f0: "mipc_init", 0x7f550: "mipc_msg_init",
        0x7f574: "mipc_msg_set_timeout_once",
        0x7f598: "mipc_msg_sync_timeout_with_cause",
        0x7f624: "mipc_msg_get_val_ptr", 0x7f6a8: "mipc_msg_deinit",
        0x7f6b0: "mipc_msg_deinit", 0x7f6b4: "mipc_deinit",
    }.items():
        mnemonic, operand = instruction(addr)
        assert mnemonic == "bl" and entries[int(operand[1:], 0)] == name
    print("B4.1 MIPC141 source ABI: endpoint/client, tags, words, cleanup verified")


if __name__ == "__main__":
    assert len(sys.argv) == 2, "usage: test_b41_mipc_producer.py MNLD"
    check(Path(sys.argv[1]))
