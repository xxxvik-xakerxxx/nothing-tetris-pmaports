#!/usr/bin/env python3
"""Offline execution of ONLY the pinned tag accessor, inside Unicorn.

No dlopen/native ELF execution, init, modem, sockets, engine or phone operations.
The hashmap lookup is intercepted to supply a fixture-owned node; this proves
accessor ABI/length behavior, NOT modem framing or parser/transport safety.
One emulator, two coalesced mappings, explicit hook cleanup; no ownership cycles.
"""
import argparse
import json
from pathlib import Path

from b41_mipc_elf_audit import API, export, read_elf
from b41_mipc_exact_contract import MIPC_SHA, NEEDED, contract


def inventory(image):
    exports = [export(image, name) for name in API]
    imports = [s for s in image["symbols"] if s["undefined"] and s["name"]]
    by_name = {s["name"]: s for s in image["symbols"] if not s["undefined"]}
    return {"sha256": image["sha256"], "needed": image["dynamic"]["DT_NEEDED"],
            "required_exports": [{k: s[k] for k in ("name", "address", "size", "binding", "visibility")}
                                 for s in exports],
            "imports": [{k: s[k] for k in ("name", "type", "binding")} for s in imports],
            "internal_api_interposition": "getter calls mipc_hashmap_get through PLT14ef0; "
                                          "default-visible exports require isolated legitimate loader ownership",
            "length_contract": "getter third parameter uint16_t*, not uint32_t* or size_t*",
            "hashmap_get_export": {k: by_name["mipc_hashmap_get"][k]
                                   for k in ("address", "size", "binding", "visibility")},
            "dependency_files_audited": False,
            "additional_vendor_dependency_basenames": NEEDED[:3],
            "engine_readiness": False}


def run(image):
    # Lazy import permits ELF inventory use without installing Unicorn.
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm64_const import (UC_ARM64_REG_PC, UC_ARM64_REG_SP,
                                    UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                    UC_ARM64_REG_X2, UC_ARM64_REG_LR,
                                    UC_ARM64_REG_TPIDR_EL0)
    contract(image)
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    start = min(s["address"] for s in image["segments"]) & ~4095
    end = max(s["address"] + len(s["data"]) for s in image["segments"])
    uc.mem_map(start, (end + 4095 & ~4095) - start)
    for segment in image["segments"]:
        uc.mem_write(segment["address"], segment["data"])
    ram, ram_size = 0x200000, 0x40000
    uc.mem_map(ram, ram_size)
    message, node, tlv, length_ptr = ram + 0x100, ram + 0x200, ram + 0x300, ram + 0x400
    tls, stop, stack = ram + 0x500, ram + 0x1000, ram + ram_size - 0x100
    state = {"node": node, "expected_tag": 0, "lookups": 0, "returned": False}

    def hook(cpu, address, size, user_data):
        if address == 0x14ef0:
            # Actual accessor passes masked uint16 key and a two-byte key size.
            assert cpu.reg_read(UC_ARM64_REG_X0) == ram + 0x800
            assert cpu.reg_read(UC_ARM64_REG_X2) == 2
            key = cpu.reg_read(UC_ARM64_REG_X1)
            assert int.from_bytes(cpu.mem_read(key, 2), "little") == state["expected_tag"]
            cpu.reg_write(UC_ARM64_REG_X0, state["node"])
            cpu.reg_write(UC_ARM64_REG_PC, cpu.reg_read(UC_ARM64_REG_LR))
            state["lookups"] += 1
        elif address == stop:
            state["returned"] = True
            cpu.emu_stop()

    handle = uc.hook_add(UC_HOOK_CODE, hook)
    results = []
    try:
        uc.mem_write(message + 0x18, (ram + 0x800).to_bytes(8, "little"))
        uc.reg_write(UC_ARM64_REG_TPIDR_EL0, tls)
        # Distinct canary checks for byte writes beyond uint16 output extent.
        for tag in (0, 0x101, 0x102, 0x103, 0x8101):
            for length in (0, 1, 2, 3, 4, 8, 65535):
                for length_output in (False, True):
                    state.update(node=node, expected_tag=tag & 0x7fff,
                                 lookups=0, returned=False)
                    uc.mem_write(node + 0x20, tlv.to_bytes(8, "little"))
                    uc.mem_write(tlv, (tag & 65535).to_bytes(2, "little") + length.to_bytes(2, "little"))
                    uc.mem_write(length_ptr, b"\xa5" * 8)
                    uc.reg_write(UC_ARM64_REG_X0, message)
                    uc.reg_write(UC_ARM64_REG_X1, tag)
                    uc.reg_write(UC_ARM64_REG_X2, length_ptr if length_output else 0)
                    uc.reg_write(UC_ARM64_REG_SP, stack)
                    uc.reg_write(UC_ARM64_REG_LR, stop)
                    uc.emu_start(0xf200, stop + 4, timeout=100000, count=200)
                    assert state["returned"] and state["lookups"] == 1
                    assert uc.reg_read(UC_ARM64_REG_X0) == tlv + 4
                    expected = length.to_bytes(2, "little") + b"\xa5" * 6 if length_output else b"\xa5" * 8
                    assert bytes(uc.mem_read(length_ptr, 8)) == expected
                    results.append({"tag": tag, "length": length, "length_output": length_output})
        for missing in ("node", "value"):
            state.update(node=0 if missing == "node" else node,
                         expected_tag=0x101, lookups=0, returned=False)
            uc.mem_write(node + 0x20, bytes(8))
            uc.mem_write(length_ptr, b"\xa5" * 8)
            uc.reg_write(UC_ARM64_REG_X0, message)
            uc.reg_write(UC_ARM64_REG_X1, 0x101)
            uc.reg_write(UC_ARM64_REG_X2, length_ptr)
            uc.reg_write(UC_ARM64_REG_SP, stack)
            uc.reg_write(UC_ARM64_REG_LR, stop)
            uc.emu_start(0xf200, stop + 4, timeout=100000, count=200)
            assert state["returned"] and state["lookups"] == 1
            assert uc.reg_read(UC_ARM64_REG_X0) == 0
            assert bytes(uc.mem_read(length_ptr, 8)) == bytes(2) + b"\xa5" * 6
            results.append({"missing": missing})
    finally:
        uc.hook_del(handle)
        # Old distro Unicorn has no explicit close; removing the hook breaks
        # its callback reference, and the entire oracle uses only one Uc.
        if hasattr(uc, "close"):
            uc.close()
    return {"accessor_vectors_passed": len(results),
            "uint16_length_write_and_surrounding_canary_verified": True,
            "short_values_return_nonnull": True,
            "null_node_or_value_returns_null_and_length_zero": True,
            "parser_transport_or_engine_executed": False, "engine_readiness": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("libmipc", type=Path)
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    image = read_elf(args.libmipc, MIPC_SHA)
    contract(image)
    report = {"inventory": inventory(image)}
    if not args.inventory_only:
        report["oracle"] = run(image)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
