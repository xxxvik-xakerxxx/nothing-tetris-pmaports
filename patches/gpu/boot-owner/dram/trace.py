#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded static DRAM refinement using authenticated inputs; no RV execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from audit_boot import audit, decode_window, expect, expect_lk, signed_lk
from audit_boot import read_bounded, read_private_snapshot, require
from audit_startup import address_pair

PRIMARY_WINDOWS = (
    (0x1df8, 0x1eb0, '5814c04e5cef7deaabdc32db602b9a6595cbb1eefb7bb83a9803f23cb29c477d'),
    (0x7a3e, 0x7a70, 'b5f28388c511f92c04f04d08f42accabc26ffa5b4a6f79ca10ac66741c3bc031'),
    (0xfe94, 0xff16, 'aec272ef00e16c5c79f40e7702c4dc809d6f92a1778a6f53ae6d88a900a51268'),
    (0xa3c8, 0xa44e, '02ad3ef3b190059133e7e3d87805239357ef3b2ad03576b25ab17fb3b0961f1e'),
)


def refine(primary, code):
    for start, end, digest in PRIMARY_WINDOWS:
        require(hashlib.sha256(primary[start:end]).hexdigest() == digest, 'DRAM instruction window drift')
    for start, end, digest in (
        (0x74da0, 0x7524c, '37fbf6132fc3fbf21e3cd3a9918b348d600933ee1e0f879a4a957d242eea4434'),
        (0x7db00, 0x7dcec, '36b4f576ddc910ca0b65547c17f0377ef9b433b7475f66593e6c4704d6b0c00e'),
    ):
        require(hashlib.sha256(code[start:end]).hexdigest() == digest, 'LK reader window drift')
    require(struct.unpack_from('<6I', primary) == (0x0ac0006f, 0, 0, 0, 0, 0),
            'signed primary six-word header drift')
    require(primary[0x1690d:].split(b'\0', 1)[0] ==
            b'[E]%s: size(0x%llx) is not 4KB aligned\n' and
            primary[0x17244:].split(b'\0', 1)[0] == b'gpumpu_init_page_table',
            'helper diagnostic identity')
    helper = decode_window(primary, 0xfe94, 0xff16, (0xfe9a, 0xfec2))
    for check in ((0xfe98, 'c.mv', 's2, a2'), (0xfe9e, 'c.beqz', 'a2, 0x18'),
                  (0xfeb6, 'srli', 'a2, a0, 0x14'), (0xfebe, 'slli', 'a3, a0, 0xc'),
                  (0xfece, 'sw', 'a3, -0x488(s0)'), (0xfed2, 'sw', 'a2, 4(s3)'),
                  (0xfed6, 'jal', '-0x5a88'), (0xfefc, 'c.mv', 'a0, s1'),
                  (0xfefe, 'c.li', 'a1, 0'), (0xff00, 'c.mv', 'a2, s2'),
                  (0xff02, 'jal', '-0x84c4')):
        expect(helper, *check)
    fill = decode_window(primary, 0x7a3e, 0x7a70, (0x7a4e, 0x7a5c, 0x7a62, 0x7a66))
    for check in ((0x7a3e, 'or', 'a3, a0, a2'), (0x7a42, 'c.add', 'a2, a0'),
                  (0x7a44, 'c.andi', 'a3, 3'), (0x7a46, 'c.beqz', 'a3, 0x12'),
                  (0x7a52, 'bne', 'a3, a2, -4'), (0x7a6a, 'bltu', 'a3, a2, -4')):
        expect(fill, *check)
    early = decode_window(primary, 0x1df8, 0x1eb0)
    for check in ((0x1dfc, 'auipc', 't0, 0xffffe'), (0x1e00, 'addi', 't0, t0, 0x208'),
                  (0x1e04, 'lw', 't0, 0(t0)'), (0x1e08, 'srli', 't0, t0, 0x1c'),
                  (0x1e40, 'auipc', 't0, 0xffffe'), (0x1e44, 'addi', 't0, t0, 0x1c4'),
                  (0x1e54, 'lw', 't1, 0xc(t0)'), (0x1e58, 'lw', 't0, 4(t0)')):
        expect(early, *check)
    require(address_pair(early, 0x1dfc, 0x1e00, 't0') == 4 and
            address_pair(early, 0x1e40, 0x1e44, 't0') == 4, 'primary header base drift')
    for check in ((0x74dc8, 'mov', 'x21, x2'), (0x75024, 'mov', 'x1, x21'),
                  (0x75030, 'bl', '#0x67edc'), (0x75180, 'ldr', 'w25, [x19, #4]'),
                  (0x7518c, 'add', 'x24, x27, #0x200')):
        expect_lk(code, *check)
    return {
        'rv33_words': [
            {'pc': 0xfe9a, 'word': '08c66633', 'opcode': 0x33,
             'context': 'error diagnostic tests 4KB size alignment; exact instruction semantics unproven'},
            {'pc': 0xfec2, 'word': '67458633', 'opcode': 0x33,
             'context': 'between low PA <<12 and high PA >>20 production; exact instruction semantics unproven'}],
        'gpr6': {'argument': 'GPR6 value, representing PA >>12', 'size': 0x400000,
                 'callee': 0xfe94, 'mapped_address_helper': 0xa44e,
                 'zero_fill_candidate': {'callee': 0x7a3e, 'argument_value': 0,
                                         'length': 0x400000,
                                         'boundary': 'four vendor words inside the fill-shaped loop are NOT decoded'},
                 'classification': 'workspace allocation is concrete; initialized input-table requirement not established',
                 'not_proven': ['exact OP-0x33 effects', 'full zero-fill semantics',
                                'secure region-12 protection/visibility', 'pre-start absence of workspace reads']},
        'gpr0': {'lk_register_value': '1MiB staging PA (not mapped base+24)',
                 'lk_reader_destination': 'mapped base+24', 'lk_reader': 0x74da0,
                 'ordinary_member_data_read': 0x75030, 'data_offset': 512,
                 'prefix': {'bytes': 24, 'producer': 'none established in inspected LK caller/reader',
                            'consumer': 'none established; do not fabricate a prefix'},
                 'different_signed_primary_header': {'bytes': 24, 'words': [0x0ac0006f, 0, 0, 0, 0, 0],
                      'reader': 0x1df8, 'pointer_field': 4, 'copy_count_field': 16,
                      'copy_source_field': 12, 'copy_destination_field': 8,
                      'pointer_field_value': 0, 'copy_count': 0,
                      'scope': 'early cold helper reads the in-SRAM primary header, not staging-prefix contents; no copy iterations'},
                 'boundary': 'whole firmware GPR0/warm-save producer-reader contract still unresolved'},
        'native_candidate': 'private CMA-backed 6MiB physical workspace, exclusive loan, PA>>12 word; no GPR writes',
        'activation': 'absent; no new code has a shipping caller or a hardware-publication API',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'lk', 'gpueb', 'device-tree', 'module-tree', 'linux-tree'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    primary, lk = read_private_snapshot(args.snapshot), read_bounded(args.lk, 8 * 1024 * 1024)
    base = audit(primary, lk, read_bounded(args.gpueb, 2 * 1024 * 1024),
                 args.device_tree, args.module_tree, args.linux_tree)
    result = refine(primary, signed_lk(lk))
    result['sources'] = base['sources']
    result['container_sha256'] = base['container_sha256']
    result['cache_comparison'] = json.loads((HERE / 'SOURCE-PINS.json').read_text())[
        'comparison_only_cache_header']
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
