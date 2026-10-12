#!/usr/bin/env python3
"""Read-only B4.1 ELF inspection. No native loading or instruction execution."""
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA


def sections(image):
    d = image.data
    offset = struct.unpack_from("<Q", d, 40)[0]
    size, count = struct.unpack_from("<HH", d, 58)
    if size != 64 or offset + size * count > len(d):
        raise ValueError("invalid ELF section headers")
    return [struct.unpack_from("<II4QII2Q", d, offset + i * size) for i in range(count)]


def relative_relocations(image):
    result = {}
    for s in sections(image):
        if s[1] != 4:
            continue
        if s[9] != 24 or s[4] + s[5] > len(image.data):
            raise ValueError("invalid ELF relocations")
        for offset in range(s[4], s[4] + s[5], 24):
            address, info, addend = struct.unpack_from("<QQq", image.data, offset)
            if info & 0xffffffff == 1027:  # R_AARCH64_RELATIVE
                result[address] = addend
    return result


def dynamic_symbols(image):
    result = {}
    all_sections = sections(image)
    for s in all_sections:
        if s[1] != 11:
            continue
        strings = all_sections[s[6]]
        names = image.data[strings[4]:strings[4] + strings[5]]
        if s[9] != 24 or s[4] + s[5] > len(image.data):
            raise ValueError("invalid ELF dynamic symbols")
        for offset in range(s[4], s[4] + s[5], 24):
            name, _, _, _, address, length = struct.unpack_from("<IBBHQQ", image.data, offset)
            result[names[name:].split(b"\0", 1)[0].decode("ascii")] = (address, length)
    return result


def load(mnld, library):
    return PinnedImage(Path(mnld).read_bytes(), MNLD_SHA), PinnedImage(Path(library).read_bytes(), LIB_SHA)


def describe(mnld, library):
    symbols = dynamic_symbols(library)
    table = struct.unpack("<104H", mnld.read(0x22bc0, 208))
    types = (250, 256, 257, 258, 259, 260, 261, 262, 264)
    return {
        "mnld_sha256": MNLD_SHA, "libmnl_sha256": LIB_SHA,
        "method": "static ELF/disassembly only",
        "reverse_abstract_name": mnld.read(0xc9e5, 13).rstrip(b"\0").decode("ascii"),
        "reverse_sockaddr_length": 15,
        "forward_service_implemented": False,
        "missing_agps_receiver_cleared": False,
        "receiver_branches": {str(t): hex(0x3a588 + table[t - 200] * 4) for t in types},
        "native_functions": {k: [hex(x) for x in symbols[k]] for k in (
            "mtk_agps_set_param", "mtk_agps_set_param_with_payload_len")},
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: private_evidence.py PINNED_MNLD PINNED_LIBMNL")
    print(json.dumps(describe(*load(*sys.argv[1:])), indent=2, sort_keys=True))
