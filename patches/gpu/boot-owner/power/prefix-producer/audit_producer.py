#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static signed-LK address/caller inventory, never instruction execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from generate_report import PINS, git_source, require

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
SPM = 0x1c001eb4


def hex_offsets(code, value, size):
    needle = value.to_bytes(size, 'little')
    return [hex(i) for i in range(len(code) - size + 1) if code[i:i + size] == needle]


def direct_refs(code, target):
    result = []
    for offset in range(0, len(code) - 3, 4):
        word = struct.unpack_from('<I', code, offset)[0]
        if word >> 26 not in (0x25, 0x05):
            continue
        displacement = word & 0x3ffffff
        if displacement & 0x2000000:
            displacement -= 0x4000000
        if offset + displacement * 4 == target:
            result.append(hex(offset))
    return result


def constant_memory_inventory(code):
    """Conservative local constant definitions, not a firmware emulator/CFG proof.

    Decode the entire aligned payload (including data). Only retain immediate,
    copied and literal constant address definitions inside basic blocks. Drop
    unknown writes, branch joins and call-clobbered registers. Indexed/dynamic
    addresses and transitive external effects remain explicitly unresolved.
    """
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM, CS_AC_WRITE
    from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_REG, ARM64_OP_MEM
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    decoder.detail = True
    decoder.skipdata = True
    facts, memory, seeds = {}, [], []

    def register(ins, reg):
        name = ins.reg_name(reg)
        return 'x' + name[1:] if name.startswith('w') else name

    for ins in decoder.disasm(code, 0):
        if not ins.id:
            facts.clear()
            continue
        ops = ins.operands
        if ins.mnemonic == 'movk' and len(ops) > 1 and ops[1].type == ARM64_OP_IMM and ops[1].imm == 0x1c00:
            seeds.append(hex(ins.address))
        for op in ops:
            if op.type != ARM64_OP_MEM:
                continue
            base = facts.get(register(ins, op.mem.base))
            if base is None or op.mem.index or ins.writeback:
                continue
            address = (base + op.mem.disp) & ((1 << 48) - 1)
            if 0x1c000000 <= address < 0x1c010000:
                memory.append({'offset': hex(ins.address), 'address': hex(address),
                               'instruction': ins.mnemonic,
                               'write': bool(op.access & CS_AC_WRITE)})
        value = None
        if len(ops) >= 2 and ops[0].type == ARM64_OP_REG:
            name = ins.reg_name(ops[0].reg)
            dest = register(ins, ops[0].reg)
            if ins.mnemonic in ('mov', 'movz', 'adr', 'adrp'):
                if ops[1].type == ARM64_OP_IMM:
                    value = ops[1].imm << ops[1].shift.value
                elif ops[1].type == ARM64_OP_REG:
                    value = facts.get(register(ins, ops[1].reg))
            elif ins.mnemonic == 'movk' and ops[1].type == ARM64_OP_IMM and dest in facts:
                shift = ops[1].shift.value
                value = (facts[dest] & ~(0xffff << shift)) | (ops[1].imm << shift)
            elif ins.mnemonic in ('add', 'sub') and len(ops) == 3 and ops[1].type == ARM64_OP_REG and ops[2].type == ARM64_OP_IMM:
                base = facts.get(register(ins, ops[1].reg))
                if base is not None:
                    delta = ops[2].imm << ops[2].shift.value
                    value = base + (delta if ins.mnemonic == 'add' else -delta)
            elif ins.mnemonic in ('ldr', 'ldrsw') and ops[1].type == ARM64_OP_IMM:
                offset = ops[1].imm
                size = 8 if name.startswith('x') and ins.mnemonic == 'ldr' else 4
                if 0 <= offset <= len(code) - size:
                    value = int.from_bytes(code[offset:offset + size], 'little', signed=ins.mnemonic == 'ldrsw')
        _, writes = ins.regs_access()
        for reg in writes:
            facts.pop(register(ins, reg), None)
        if value is not None:
            facts[dest] = value & (0xffffffff if name.startswith('w') else 0xffffffffffffffff)
        if ins.mnemonic in ('bl', 'blr'):
            for reg in range(19):
                facts.pop('x' + str(reg), None)
            facts.pop('x30', None)
        elif ins.mnemonic in ('b', 'br', 'ret', 'eret', 'smc', 'hvc', 'cbz', 'cbnz', 'tbz', 'tbnz') or ins.mnemonic.startswith('b.'):
            facts.clear()
    return {'spm_high_movk_candidates': seeds, 'constant_spm_memory_candidates': memory,
            'target_candidates': [item for item in memory if int(item['address'], 16) == SPM],
            'scope': 'all aligned signed payload bytes; local constants only, data may decode as instructions; no indirect/dynamic writer exclusion'}


def trace(code):
    from audit_gpueb_lk import expect
    require(len(code) == PINS['lk_payload_bytes'] and hashlib.sha256(code).hexdigest() == PINS['lk_payload_sha256'], 'signed LK identity mismatch')
    for span, digest in PINS['lk_windows'].items():
        lo, hi = (int(x, 16) for x in span.split('-'))
        require(hashlib.sha256(code[lo:hi]).hexdigest() == digest, 'LK window drift: ' + span)
    for check in (
        (0x40, 'stp', 'x0, x1, [x9], #0x10'), (0x44, 'stp', 'x2, x3, [x9]'),
        (0xea3c, 'adr', 'x1, #0xea64'), (0xfa58, 'bl', '#0xea10'),
        (0xec04, 'bl', '#0x331e4'), (0xec28, 'cbnz', 'w22, #0xeed4'),
        (0x332d4, 'bl', '#0x74da0'), (0x332d8, 'tbnz', 'w0, #0x1f, #0x33494'),
        (0x332e4, 'bl', '#0x5e74'),
        (0x33400, 'mov', 'w0, #0x410'), (0x33410, 'movk', 'w0, #0x8200, lsl #16'),
        (0x33404, 'mov', 'w1, #0x5731'), (0x33414, 'movk', 'w1, #0xda06, lsl #16'),
        (0x33418, 'mov', 'w2, #1'), (0x33408, 'ldr', 'x3, [x24, #0xe88]'),
        (0x3341c, 'mov', 'w4, #0x10000'), (0x33438, 'bl', '#0x188dc'),
        (0x188dc, 'smc', '#0'),
        (0xed58, 'bl', '#0x16eb0'), (0x16eb0, 'mov', 'w0, wzr'), (0x16eb4, 'ret', ''),
        (0xed94, 'bl', '#0x1eb88'),
        (0x1eb74, 'ldr', 'w8, [x8]'), (0x1ebc8, 'ldr', 'w8, [x24]'),
        (0x1e194, 'ldr', 'w5, [x21, #0xaa4]'), (0x1e42c, 'ldr', 'w5, [x24, #0xaa4]'),
        (0x1ebd8, 'ldr', 'w2, [x24]'), (0x1ebe0, 'tbnz', 'w2, #0xd, #0x1ec54'),
        (0x1efa8, 'ldr', 'w3, [x24]'),
    ):
        expect(code, *check)
    return {
        'lk_payload_sha256': PINS['lk_payload_sha256'],
        'address_inventory': constant_memory_inventory(code),
        'target_literals': {'physical_u32': hex_offsets(code, SPM, 4),
                            'lk_virtual_u64': hex_offsets(code, 0xffff000000000000 | SPM, 8),
                            'offset_1eb4_u32': hex_offsets(code, 0x1eb4, 4)},
        'direct_gpueb_loader_refs': direct_refs(code, 0x1eb88),
        'reviewed_mfg0_reads': ['0x1e194', '0x1e42c', '0x1eb74', '0x1ebc8', '0x1ebd8', '0x1efa8'],
        'direct_smc_wrapper_refs': direct_refs(code, 0x188dc),
        'entry_argument_capture': '0x40/0x44 save incoming x0..x3; producer outside this capture not resolved',
        'preceding_spm_boundary': {'caller': '0xec04 -> 0x331e4',
            'firmware_reader': '0x332d4 -> 0x74da0; negative return branches away',
            'smc': '0x33438 -> 0x188dc', 'x0': '0x82000410', 'x1': '0xda065731',
            'x2': 1, 'x3': 'allocated SPM firmware reservation', 'x4': '0x10000',
            'meaning': 'actual preceding SPM-load secure call; bit9/ACK13 side effect NOT established'},
        'immediate_hook': '0xed58 -> 0x16eb0 is mov w0,wzr; ret, not a producer',
        'admission': '0x1ebc8/0x1ebd8: ACK[31:30]=3, bit12=0, bit13=1',
        'first_unresolved_boundary': 'producer of MFG0 SRAM_SLEEP_B bit9/ACK13 before loader entry: preceding secure SPM-load handler or earlier inherited state; neither selected by this inventory',
        'no_activation': 'no reconstructed writer, SMC, poll or borrowed domain is installed'}


def trace_atf(code):
    from audit_gpueb_lk import expect
    require(hashlib.sha256(code).hexdigest() == PINS['atf_payload_sha256'], 'ATF identity mismatch')
    for span, digest in PINS['atf_windows'].items():
        lo, hi = (int(x, 16) for x in span.split('-'))
        require(hashlib.sha256(code[lo:hi]).hexdigest() == digest, 'ATF window drift: ' + span)
    require(struct.unpack_from('<QIIQ', code, 0x58a80) ==
            (0x4881994c, 0x82000410, 0xc2000410, 0x48849b35), 'ATF BL LPM dispatch record drift')
    require(code[0x49b35:].split(b'\0', 1)[0] == b'MTK_SIP_BL_LPM_CONTROL', 'ATF BL LPM name drift')
    table = struct.unpack_from('<7Q', code, 0x5a808)
    require(table == (0, 0x4885a840, 0x488f5e10, 0x48819f00, 0, 0x48830eb4, 0x48830f00),
            'ATF registered platform table drift')
    for check in (
        (0x19960, 'ubfx', 'x9, x0, #0x10, #0x10'),
        (0x19964, 'ldr', 'w8, [x8, #0xc50]'), (0x19984, 'ldr', 'x6, [x8, #8]'),
        (0x19988, 'br', 'x6'),
        (0x20334, 'mov', 'w0, #6'), (0x20338, 'add', 'x1, x1, #0x560'),
        (0x2033c, 'bl', '#0x1f530'), (0x1f558, 'str', 'x1, [x10, #8]'),
        (0x1f56c, 'mov', 'w8, #0x5731'), (0x1f574, 'b.ne', '#0x1f59c'),
        (0x1f578, 'cmp', 'x3, #0x100, lsl #12'), (0x1f580, 'tbz', 'w1, #0, #0x1f59c'),
        (0x1f594, 'bl', '#0x30fd4'),
        (0x30ff0, 'str', 'x0, [x9, #0x30]'), (0x30ff4, 'str', 'x1, [x10, #0x38]'),
        (0x31030, 'bl', '#0x3195c'), (0x31060, 'ldr', 'x8, [x24, #0x40]'),
        (0x3107c, 'ldr', 'x8, [x8, #0x18]'), (0x3108c, 'blr', 'x8'),
        (0x30ba8, 'add', 'x0, x0, #0x808'), (0x30bac, 'bl', '#0x29f04'),
        (0x29f08, 'str', 'x0, [x8, #0x40]'),
        (0x19f00, 'mov', 'w8, #0x1194'), (0x19f08, 'ldr', 'w8, [x8]'),
        (0x311cc, 'blr', 'x9'),
        (0x30f34, 'bl', '#0x3a98'), (0x30f3c, 'bl', '#0x45b4'),
        (0x30f44, 'cbz', 'w20, #0x30f50'), (0x30f54, 'bl', '#0x39cc'),
        (0x39cc, 'mov', 'w8, #0x10b0'), (0x39d4, 'movk', 'w8, #0x1c00, lsl #16'),
        (0x39d8, 'str', 'w9, [x8]'),
    ):
        expect(code, *check)
    return {'payload_sha256': PINS['atf_payload_sha256'],
            'provenance': 'matching hash-pinned declared ATF payload; supplied container has no certificate pair, not independently authenticated here',
            'service_record': '0x58a80: MTK_SIP_BL_LPM_CONTROL -> 0x1994c',
            'registration': '0x2033c -> 0x1f530 registers group6 callback 0x1f560; registration code is not runtime proof',
            'selected_arguments': 'group6, UID 0x5731, action1, firmware pointer, 0x10000 bytes',
            'selected_callback': '0x1f594 -> 0x30fd4 stores firmware pointer/count and calls 0x3195c, then tail-calls 0x31048',
            'platform_table_initializer': '0x30bac -> 0x29f04 stores table0x5a808 at 0xf6040; mutable runtime identity not observed',
            'resolved_platform_callbacks': {'0x3108c': 'table+0x18 -> 0x19f00: read SPM0x1c001194',
                '0x311cc': 'table+0x28 -> 0x30eb4: PCM preparation helpers',
                '0x310f0': 'table+0x30 -> 0x30f00: SPM control helpers'},
            'conditional_spm_event': '0x30f54 -> 0x39cc -> 0x39d8 stores1 to SPM_CPU_WAKEUP_EVENT0x1c0010b0; selected state/control branch, not a MFG0 writer or unconditional boot proof',
            'first_unresolved_producer': 'SPM program/control effects after conditional PCM preparation/event or earlier preloader/EL3 MFG0 SRAM_SLEEP_B initialization; actual bit9 writer/ACK13 state producer not selected',
            'limits': 'no MFG0 bit9 writer/ACK13 producer proven by this dispatch trace; firmware-only origin is NOT established; no secure call is imported into loader'}


def check_nos(tree):
    path = PINS['spm_header']
    raw = git_source(tree, PINS['device_modules'], path)
    require(hashlib.sha256(raw).hexdigest() == PINS['spm_header_sha256'], 'NOS register definitions drift')
    source = raw.decode()
    for marker in ('MFG0_PWR_CON                   (SPM_BASE + 0xEB4)',
        'SPM_CPU_WAKEUP_EVENT           (SPM_BASE + 0x0B0)',
        'MFG0_SRAM_SLEEP_B_LSB               (1U << 9)',
        'SC_MFG0_SRAM_PDN_ACK_LSB            (1U << 12)',
        'SC_MFG0_SRAM_SLEEP_B_ACK_LSB        (1U << 13)'):
        require(marker in source, 'MFG0 register field definition drift')
    return {'path': path, 'line': 2879, 'sha256': PINS['spm_header_sha256'],
            'bit9': 'MFG0_SRAM_SLEEP_B', 'bit13': 'SC_MFG0_SRAM_SLEEP_B_ACK; status, not a permission cookie',
            'limits': 'register naming does not identify who initialized the control bit'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lk', type=Path, required=True)
    parser.add_argument('--atf', type=Path, required=True)
    parser.add_argument('--device-tree', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    from audit_gpueb_b41 import signed_lk, pinned_atf, read_bounded
    report = trace(signed_lk(read_bounded(args.lk, 8 * 1024 * 1024)))
    report['nos'] = check_nos(args.device_tree)
    report['atf'] = trace_atf(pinned_atf(read_bounded(args.atf, 900752)))
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    target = HERE / 'SOURCE-EVIDENCE.json'
    if args.check:
        require(target.read_text() == text, 'SOURCE-EVIDENCE.json is stale')
    else:
        target.write_text(text)
    print('Signed-LK producer inventory checked; producer remains unresolved')


if __name__ == '__main__':
    main()
