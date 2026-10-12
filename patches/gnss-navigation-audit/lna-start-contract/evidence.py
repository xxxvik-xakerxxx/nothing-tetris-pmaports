#!/usr/bin/env python3
"""Pinned static LNA producer/consumer evidence; never loads or executes ELF."""
from hashlib import sha256
from pathlib import Path
import json
import struct
import sys

import capstone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "native-agps-receiver"))
from private_evidence import load, MNLD_SHA, LIB_SHA

# Half-open virtual-address windows. Hash every byte, including non-anchor code.
WINDOWS = {
    "producer_init": ("mnld", 0x62b54, 0x62bd0, "85302da2452938b9eeaff566af4eac74c65c207b7d7e327a3ff2585f602a66c2"),
    "producer_ioctl": ("mnld", 0x6344c, 0x6349c, "37e7782be7011be06361b7e7344e10d717ef5b683b274f40d3348ab2b4721682"),
    "ioctl_veneer": ("mnld", 0x85880, 0x85890, "be24b465289a6a5ed127e2e9cff6a317f4cf1043ebdd0eaae5d6c3b31f366530"),
    "first_pointer": ("lib", 0x52e6f0, 0x52e708, "dd5e14a500f0628adbadbc9ed76215d449b2f66980455e2866eb77b66044a332"),
    "first_copy": ("lib", 0x52e708, 0x52e740, "4b8295b7593eb368a5303e92db5da3557219592858f557f79ec7237e8782536c"),
    "family_index": ("lib", 0x52e868, 0x52e870, "b801f448799972b9fba4408769fe0f0e6d35e0090e6a9579d200246a97f81cfc"),
    "family_lookup": ("lib", 0x52ea3c, 0x52ea84, "571beb4a7f6ed8bcc1cfcbfb6cbe4cf1953bf0b851078774c06651b01085f6c3"),
    "dsp_call": ("lib", 0x52f2a4, 0x52f2c8, "d48d0739e9cc5aadd03d1e6ff05726525aec9e1afe040bc274d7f257b08eb605"),
    "dsp_init": ("lib", 0x52f600, 0x52f6b8, "e3474813ae11d7dcb73a8fc7954357ada5b8fc272c22f4ee6708289ced3f570e"),
    "dsp_wrapper": ("lib", 0x55471c, 0x554748, "5767e1175c8489aa548c7eca4d79dca5e1e587252329a53f68fce538d941da11"),
    "dsp_dispatch": ("lib", 0x4f3634, 0x4f3698, "8d4747f9ae2705463531dcb48bd03469d5c8ed73bac8b38894c6fc0530bcffd4"),
    "consumer_config": ("lib", 0x4f0bdc, 0x4f0c14, "424d2d265fe77dbe23deaa25c00648830e4a4d04bda301efb2dd43a043114f7d"),
    "config_save": ("lib", 0x4f2240, 0x4f2260, "23b9d3b9ac6012ab53f016ab59dae3478bbc28d8137a17599d5f250e34899e96"),
    "config_restore": ("lib", 0x4f2588, 0x4f25a4, "f782dedcd05295e8e8f964b25c546710b0b88e1e6c48c7d3f9d0ee6d6dbdac95"),
    "consumer_dispatch": ("lib", 0x4f287c, 0x4f28b8, "b42752aaddac2154f25b7ac0ddd95e1f3b17c996980532edc59d4aa1276eafde"),
    "consumer_rejoin": ("lib", 0x4f3000, 0x4f3014, "64560afd9914fe71be4a44266361f1418b9903a8681602e74a04ce435549017f"),
    "consumer_lna": ("lib", 0x4f29e0, 0x4f2a4c, "0ea2339b77ff7b6921bcaf7bf0a12f976112fd36e3f663f6def5110ff461ba67"),
    "payload_call": ("lib", 0x4f2cc8, 0x4f2cec, "b7c58da7bc8dadfa29f6a827a0a16f6ab0c3a4ca20811afed2a92aeb26fe3865"),
    "serialize_payload": ("lib", 0x5549fc, 0x554a14, "f1a7ab62de3c8aba61a7fd3de14643c1e8627eb26672d115c268703018afbaa3"),
}

ANCHORS = {
    "producer_init": {
        0x62b64: ("adr", "x20, #0xde520"),
        0x62bcc: ("stp", "w9, wzr, [sp, #0x90]"),
    },
    "producer_ioctl": {
        0x63450: ("ldr", "w0, [x8, #0x798]"),
        0x63454: ("add", "x2, sp, #0x94"),
        0x63458: ("mov", "w1, #0x10"),
        0x6345c: ("bl", "#0x85880"),
        0x63460: ("tbz", "w0, #0x1f, #0x63484"),
        0x63480: ("bl", "#0x84f30"),
        0x6348c: ("ldr", "w9, [sp, #0x94]"),
        0x63490: ("adrp", "x10, #0xde000"),
        0x63498: ("str", "w9, [x10, #0x574]"),
    },
    "ioctl_veneer": {0x85884: ("ldr", "x17, [x16, #0xd70]")},
    "first_pointer": {0x52e6f4: ("ldr", "x24, [x24, #0x5b8]")},
    "first_copy": {
        0x52e728: ("ldp", "q0, q1, [x2, #0x50]"),
        0x52e734: ("stp", "q0, q1, [x24, #0x50]"),
    },
    "family_lookup": {
        0x52ea3c: ("ldr", "w9, [x24, #0x30]"),
        0x52ea44: ("ldr", "x10, [x10, #0xb00]"),
        0x52ea54: ("ldr", "w11, [x11, #4]"),
        0x52ea58: ("cmp", "w9, w11"),
        0x52ea5c: ("b.eq", "#0x52ea74"),
        0x52ea74: ("ldr", "w8, [x10, x8]"),
        0x52ea80: ("strb", "w8, [x26]"),
    },
    "family_index": {0x52e868: ("mov", "x8, xzr")},
    "dsp_call": {
        0x52f2b8: ("ldr", "x0, [x0, #0x5b8]"),
        0x52f2bc: ("bl", "#0x6e5520"),
    },
    "dsp_init": {
        0x52f600: ("mov", "x19, x0"),
        0x52f6a0: ("mov", "x0, x19"),
        0x52f6a4: ("mov", "w1, #1"),
        0x52f6a8: ("bl", "#0x55471c"),
    },
    "dsp_wrapper": {0x554728: ("bl", "#0x4f3634")},
    "dsp_dispatch": {
        0x4f3644: ("mov", "x20, x0"),
        0x4f3650: ("b.eq", "#0x4f366c"),
        0x4f366c: ("mov", "x0, x20"),
        0x4f3674: ("bl", "#0x4f0bdc"),
    },
    "consumer_config": {0x4f0c00: ("mov", "x26, x0")},
    "config_save": {0x4f224c: ("stp", "x23, x26, [sp, #0xa0]")},
    "config_restore": {0x4f259c: ("ldr", "x26, [sp, #0xa8]")},
    "consumer_dispatch": {
        0x4f287c: ("ldr", "w8, [x26, #0x30]"),
        0x4f2880: ("mov", "w9, #0x9a90"),
        0x4f2884: ("add", "w9, w8, w9"),
        0x4f2888: ("cmp", "w9, #0x22"),
        0x4f288c: ("b.hi", "#0x4f3000"),
    },
    "consumer_rejoin": {0x4f3010: ("b", "#0x4f28b4")},
    "consumer_lna": {
        0x4f29e0: ("mov", "w11, #-0x988f"),
        0x4f29e4: ("ldrb", "w9, [x22]"),
        0x4f29f4: ("b.ne", "#0x4f2a0c"),
        0x4f2a10: ("mov", "w10, #0x48"),
        0x4f2a14: ("mov", "w12, #-0x99ce"),
        0x4f2a1c: ("b.eq", "#0x4f2a40"),
        0x4f2a20: ("cmp", "w9, #4"),
        0x4f2a24: ("b.lo", "#0x4f2a40"),
        0x4f2a28: ("ldr", "w10, [x26, #0x54]"),
        0x4f2a2c: ("mov", "w11, #-0x99ce"),
        0x4f2a30: ("cmp", "w8, w11"),
        0x4f2a34: ("mov", "w8, #0xa"),
        0x4f2a3c: ("csel", "w11, w11, w8, eq"),
        0x4f2a40: ("strb", "w10, [sp, #0x712]"),
        0x4f2a48: ("strb", "w11, [sp, #0x713]"),
    },
    "payload_call": {
        0x4f2cd4: ("add", "x2, sp, #0x6b0"),
        0x4f2cd8: ("mov", "w0, #8"),
        0x4f2cdc: ("mov", "w1, #0x35"),
        0x4f2ce4: ("bl", "#0x554828"),
    },
    "serialize_payload": {
        0x5549fc: ("ldur", "x1, [sp, #6]"),
        0x554a08: ("sub", "w2, w8, #4"),
        0x554a10: ("bl", "#0x683b9c"),
    },
}

DRIVER_SOURCE_SHA = "e86503641fed4316b87f1de1aee4f367926ab2aa5010b7d77d7c938174a5cd7d"


def verify_driver_source(data):
    if sha256(data).hexdigest() != DRIVER_SOURCE_SHA:
        raise ValueError("changed inspected mcudl source")
    source = data.decode("ascii")
    clock = source.index("\tcase GPSDL_IOC_CO_CLOCK_FLAG:")
    disabled = source.index("#if 0", clock)
    end = source.index("#endif\n\tcase GPSDL_IOC_GPS_HW_SUSPEND:", disabled)
    if "\tcase GPSDL_IOC_GET_GPS_LNA_PIN:" not in source[disabled:end]:
        raise ValueError("case16 not excluded")
    default = source[source.index("\tdefault:\n", end):source.index("\n\treturn retval;", end)]
    if "retval = -EFAULT;" not in default or "copy_to_user" in default:
        raise ValueError("wrong unsupported ioctl result")
    return {"source_sha256": DRIVER_SOURCE_SHA, "case16_compiled": False,
            "default_errno": "EFAULT", "default_copies_output": False}


def verify_window(name, data):
    _, start, end, digest = WINDOWS[name]
    if len(data) != end - start or sha256(data).hexdigest() != digest:
        raise ValueError(f"changed instruction window: {name}")
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    code = {i.address: (i.mnemonic, i.op_str) for i in decoder.disasm(data, start)}
    if len(code) != len(data) // 4:
        raise ValueError(f"incomplete decode: {name}")
    for address, expected in ANCHORS[name].items():
        if code[address] != expected:
            raise ValueError(f"wrong instruction: {name}:{address:x}")
    return code


def verify(mnld, library):
    if capstone.__version__ != "5.0.6":
        raise ValueError("Capstone 5.0.6 required")
    images = {"mnld": mnld, "lib": library}
    result = {}
    for name, (kind, start, end, _) in WINDOWS.items():
        result[name] = verify_window(name, images[kind].read(start, end - start))
    if mnld.imported_symbol(0x86d70) != (1026, b"ioctl"):
        raise ValueError("wrong ioctl relocation")
    if library.imported_symbol(0x6e9188) != (1026, b"mtk_gps_dsp_init"):
        raise ValueError("wrong DSP-init relocation")
    if struct.unpack("<Q", library.read(0x6e65b8, 8))[0] != 0x71f1d0:
        raise ValueError("wrong first-config global")
    if struct.unpack("<Q", library.read(0x6e7b00, 8))[0] != 0x6ee1a8:
        raise ValueError("wrong family table")
    if struct.unpack("<II", library.read(0x6ee1a8, 8)) != (5, 0xffff6878):
        raise ValueError("wrong MT6878 family")
    if struct.unpack("<Q", library.read(0x6e6670, 8))[0] != 0x717cb6:
        raise ValueError("wrong family global")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: evidence.py PINNED_MNLD PINNED_LIBMNL")
    code = verify(*load(*sys.argv[1:]))
    print(json.dumps({
        "method": "static ELF/disassembly only; no instruction execution",
        "mnld_sha256": MNLD_SHA, "libmnl_sha256": LIB_SHA,
        "stock_kernel_errno": "EFAULT (matching mcudl source, not a live receipt)",
        "port_metadata_absent_errno": "ENODATA (separate port profile)",
        "windows": {name: {hex(a): list(op) for a, op in window.items()}
                    for name, window in code.items()},
        "firmware_zero_meaning_proven": False,
        "native_init_validated": False,
    }, indent=2, sort_keys=True))
