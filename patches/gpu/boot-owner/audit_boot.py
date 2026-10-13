#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Authenticate real inputs and inspect bounded boot/DRAM contracts; no execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE.parent / 'rv33-startup')]
from audit_gpueb_b41 import signed_lk, read_bounded, read_private_snapshot, PRIMARY_BYTES
from audit_gpueb_lk import ROOT_PIN, expect as expect_lk
from audit_startup import prove_layout, decode_window, expect, immediate
from gpueb_firmware import inspect, sections, certificate, metadata, bits

PINS = json.loads((HERE / 'SOURCE-PINS.json').read_text())
LK_WINDOWS = (
    (0x1ec54, 0x1ef14, 'f86128f3592df1a3fa9a54e36a045d32eacdd6f3e3a579a09cb4ba468fe579ca'),
    (0x16ec0, 0x16ec8, '2b59db05426e0f313d72b30f3398c65721de2562a59dc46ceeba224f98d0b876'),
    (0x29754, 0x298a0, '93a5917ccf9d70615e87bc5bf2b928bee56db92fc2106b375ad51dda01f5f188'),
    (0x7ef84, 0x7f0a8, 'fbc84199b740de909977255830bc2a833e6884e84dc9b7074834471ebec3e72f'),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def pinned_source(tree, revision, path):
    return subprocess.check_output(['git', '-C', str(tree), 'show', revision + ':' + path],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}, text=True)


def trace_lk(code):
    require(hashlib.sha256(code).hexdigest() == PINS['lk_payload_sha256'], 'LK payload identity')
    for start, end, digest in LK_WINDOWS:
        require(hashlib.sha256(code[start:end]).hexdigest() == digest, 'LK window identity')
    for check in (
        (0x16ec0, 'mov', 'w0, wzr'), (0x16ec4, 'ret', ''),
        (0x1ec60, 'mov', 'w0, #0x100000'), (0x1ec64, 'mov', 'w1, #0x10000'),
        (0x1ec7c, 'mov', 'x19, x0'), (0x1ec84, 'cbz', 'w0, #0x1ed30'),
        (0x1ed38, 'mov', 'w0, #0x600000'), (0x1ed3c, 'mov', 'w1, #0x10000'),
        (0x1ed40, 'mov', 'w2, #-0x80000000'), (0x1ed4c, 'bl', '#0x140ec'),
        (0x1ed50, 'mov', 'x21, x0'),
        (0x1ecbc, 'add', 'x8, x21, #0x600, lsl #12'),
        (0x1ecc0, 'mov', 'w9, #0xc'), (0x1ecc8, 'stp', 'x21, x8, [sp, #0x18]'),
        (0x1eccc, 'str', 'w9, [sp, #0x28]'), (0x1ecd0, 'bl', '#0x7ef84'),
        (0x1ecf0, 'mov', 'x5, x19'), (0x1ecfc, 'bl', '#0x67894'),
        (0x1ed74, 'ldr', 'x8, [sp, #8]'), (0x1ed8c, 'add', 'x23, x8, #0x18'),
        (0x1ed90, 'mov', 'x2, x23'), (0x1ed94, 'bl', '#0x74da0'),
        (0x1eda8, 'mov', 'x22, #0x600'), (0x1edb0, 'movk', 'x22, #0x13c6, lsl #16'),
        (0x1edd8, 'mov', 'x0, #0x13c00000'), (0x1ede4, 'mov', 'w1, wzr'),
        (0x1ede8, 'mov', 'w2, #0x40000'), (0x1edf8, 'str', 'wzr, [x22]'),
        (0x1edfc, 'bl', '#0x6a98c'), (0x1ee20, 'lsr', 'x8, x21, #0xc'),
        (0x1ee38, 'str', 'w19, [x23]'), (0x1ee3c, 'str', 'wzr, [x23, #4]'),
        (0x1ee40, 'str', 'wzr, [x23, #0x5c]'), (0x1ee44, 'str', 'w8, [x23, #0x18]'),
        (0x7efc8, 'bl', '#0x16ea0'), (0x7efcc, 'cmp', 'w0, #2'),
        (0x7f070, 'mov', 'w0, #0x415'), (0x7f074, 'ubfx', 'x2, x20, #0xc, #0x20'),
        (0x7f078, 'ubfx', 'x3, x22, #0xc, #0x20'), (0x7f07c, 'ldr', 'w4, [x19, #0x10]'),
        (0x7f084, 'movk', 'w0, #0x8200, lsl #16'),
        (0x7f088, 'mov', 'x1, xzr'), (0x7f09c, 'bl', '#0x188dc'),
        (0x2987c, 'mov', 'w0, #0x180000'), (0x29880, 'mov', 'w1, #0x10000'),
        (0x29884, 'mov', 'w2, #-0x80000000'), (0x29890, 'bl', '#0x140ec'),
        (0x29894, 'mov', 'x20, x0'), (0x297d0, 'add', 'x8, x20, #0x180, lsl #12'),
        (0x297d4, 'mov', 'w9, #0x1f'), (0x297dc, 'stp', 'x20, x8, [sp, #8]'),
        (0x297e4, 'bl', '#0x7ef84'), (0x29800, 'rev', 'x8, x20'),
        (0x29804, 'adrp', 'x2, #0xcb000'), (0x29808, 'add', 'x2, x2, #0xbc2'),
        (0x29820, 'bl', '#0x5aa68'), (0x29824, 'mov', 'x8, #0x180000000000'),
        (0x29828, 'adrp', 'x2, #0xba000'), (0x2982c, 'add', 'x2, x2, #0xf86'),
        (0x29844, 'bl', '#0x5aa68'),
    ):
        expect_lk(code, *check)
    for offset, label in ((0xcbbc2, b'gpueb_mem_addr'), (0xbaf86, b'gpueb_mem_size')):
        require(code[offset:].split(b'\0', 1)[0] == label, 'DT publication name identity')
    return {
        'gpr0': {'value': 'low32(1 MiB staging physical base)',
                 'reader_source': 'mapped staging + 24', 'prefix_bytes': 24,
                 'prefix_initialization': 'unresolved; no prefix bytes admitted as payload',
                 'lifetime': 'LK unmaps/frees staging after BOOTREADY or timeout; not persistent Linux input'},
        'gpr6': {'value': 'MPU-table physical base >> 12', 'reservation_bytes': 0x600000,
                 'alignment': 0x10000, 'selected_upper_bound': 0x80000000, 'emi_region': 12,
                 'protection': 'caller submits [base, base+6 MiB); backend 2 is 0x82000415; return unchecked',
                 'initialization': 'no full zero or table-content producer established in this caller'},
        'linux_shared_dram': {'reservation_bytes': 0x180000, 'alignment': 0x10000,
                              'emi_region': 31, 'published_properties': ['gpueb_mem_addr', 'gpueb_mem_size'],
                              'producer': 'LK 0x29754; separate from GPR6 allocation'},
        'sram_initialization': {'bytes': 0x40000, 'after_reset_assert': 'LK 0x1edf8 -> 0x1edfc',
                                'policy': 'explicit whole-bank clear, separately from signed primary copy'},
    }


def trace_primary(primary):
    require(len(primary) == PRIMARY_BYTES and hashlib.sha256(primary).hexdigest() ==
            PINS['observed_primary_sha256'], 'observed primary identity')
    layout = prove_layout(primary)
    for start, end, digest in (
        (0x10062, 0x100e2, '3653405f30c1fd67fb96f45c09c394fc9f8015749be477e78b87262f5fd58430'),
        (0xfe94, 0xff0e, 'ee208a67a84b97a3ab3f13ef51157cae45a6db8716916ab6540c40946bb4e6f8'),
    ):
        require(hashlib.sha256(primary[start:end]).hexdigest() == digest, 'primary window identity')
    code = decode_window(primary, 0x10062, 0x100e2)
    for check in ((0x10078, 'lui', 'a1, 0x3f'), (0x10080, 'addi', 'a1, a1, 0x2b8'),
                  (0x10084, 'sw', 'a1, -0x494(a0)'),
                  (0x10088, 'lui', 'a1, 0x3f'), (0x10090, 'addi', 'a1, a1, 0x6b8'),
                  (0x10094, 'sw', 'a1, -0x490(a0)'),
                  (0x100a0, 'lui', 'a2, 0x40'), (0x100a8, 'addi', 'a2, a2, -0x2cc'),
                  (0x100b8, 'lr.w', 'a0, (a2)'), (0x100bc, 'lui', 'a2, 0x400'),
                  (0x100c0, 'c.li', 'a1, 0'), (0x100c2, 'c.li', 'a3, 0'),
                  (0x100c4, 'c.jal', '-0x230')):
        expect(code, *check)
    require(0x100c4 + immediate(code[0x100c4]) == 0xfe94, 'GPR6 helper target')
    helper = decode_window(primary, 0xfe94, 0xff0e, (0xfe9a, 0xfec2))
    expect(helper, 0xfefc, 'c.mv', 'a0, s1')
    expect(helper, 0xfefe, 'c.li', 'a1, 0')
    expect(helper, 0xff00, 'c.mv', 'a2, s2')
    expect(helper, 0xff02, 'jal', '-0x84c4')
    return {
        'signed_bytes': PRIMARY_BYTES, 'profile': 1, 'entry': layout['entry'],
        'cold_fills': layout['fills'], 'cold_fill_scope': layout['caller_dominance']['scope'],
        'stock_copy_bytes': 0x3f2b8,
        'stock_excess': {'start': PRIMARY_BYTES, 'end': 0x3f2b8,
                         'classification': 'not demonstrated BSS; no source upload from this interval'},
        'gpr6_consumer': {'read_at': 0x100b8, 'gpr_offset': 0x3fd34,
                          'helper': 0xfe94, 'size_argument': 0x400000,
                          'zero_arguments': ['a1 at entry', 'a3 at entry', 'a1 at 0xfefe'],
                          'boundary': 'opaque RV33 words and callees; not a proven 4 MiB initialization algorithm'},
        'mpu_workspace': {'starts': [0x3f2b8, 0x3f6b8],
                          'classification': 'runtime pointer stores; inside bank beyond signed primary, not executable tail proof'},
    }


def audit(snapshot, lk_container, gpueb, device_tree, module_tree, linux_tree):
    primary = trace_primary(snapshot)
    code = signed_lk(lk_container)
    lk = trace_lk(code)
    firmware = inspect(gpueb, ROOT_PIN)
    require(0 < len(gpueb) <= 2 * 1024 * 1024, 'GPUEB container exceeds input bound')
    members = sections(gpueb)
    _, fields = certificate(members[2].payload)
    require(len(members[0].payload) == PRIMARY_BYTES and
            bits(metadata(fields, 4, 2), 32).hex() == PINS['observed_primary_sha256'],
            'snapshot does not match authenticated container plaintext identity')
    revision = PINS['device_modules']
    dt = pinned_source(device_tree, revision, 'arch/arm64/boot/dts/mediatek/mt6878.dts')
    memory = pinned_source(device_tree, revision, 'drivers/gpu/mediatek/gpueb/gpueb_reserved_mem.c')
    wrapper = pinned_source(device_tree, revision, 'drivers/gpu/mediatek/gpufreq/v2/gpufreq_v2.c')
    require('<0 0x4000>' in dt and '<1 0x180000>' in dt and
            'accumlate_memory_size > gpueb_mem_size' in memory and
            'memset((void *)gpufreq_mem_va, 0, gpufreq_mem_size);' in wrapper,
            'NOS shared-memory contract changed')
    makefile = pinned_source(module_tree, PINS['modules'], 'gpu/mt6878/Makefile')
    require('mali_avalon/mali-r44p1/drivers/gpu/arm/midgard/' in makefile, 'NOS Mali selector changed')
    # Verify the pinned API source exists; never compile it or use a modified checkout.
    pinned_source(linux_tree, PINS['linux'], 'include/linux/ioport.h')
    lk['linux_shared_dram'].update(kernel_table_bytes=0x184000, excess_over_stock_reservation=0x4000)
    return {'scope': 'authenticated identity plus bounded static contracts; no firmware execution',
            'sources': {key: PINS[key] for key in ('linux', 'device_modules', 'modules')},
            'container_sha256': firmware['container_sha256'], 'primary': primary, 'lk': lk,
            'next_executable_step': 'staged one-shot reset-held full-SRAM clear, signed-primary copy and readback; retain quarantine',
            'start_boundary': ['GPR0 first-24-byte producer/consumer contract',
                               'MPU-table contents, secure protection semantics and RV33 helper effects',
                               'separate shared DRAM allocation/table size mismatch',
                               'owned reset-release/IRQ activation and real session binding'],
            'stock_overread_policy': 'not a requirement to reproduce; executable extent must come from initialized start consumers'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'lk', 'gpueb', 'device-tree', 'module-tree', 'linux-tree'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(read_private_snapshot(args.snapshot), read_bounded(args.lk, 8 * 1024 * 1024),
                       read_bounded(args.gpueb, 2 * 1024 * 1024),
                       args.device_tree, args.module_tree, args.linux_tree)
    except Exception as error:
        parser.exit(1, 'GPUEB boot inspection failed (' + type(error).__name__ + '); no report\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
