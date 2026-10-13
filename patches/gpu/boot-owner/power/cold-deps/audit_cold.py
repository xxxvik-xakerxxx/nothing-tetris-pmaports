#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Authenticate bounded cold dependency evidence; static inspection, never execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PINS = json.loads((HERE / 'SOURCE-PINS.json').read_text())
sys.path.insert(0, str(HERE.parents[2]))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_source(tree, revision, path):
    return subprocess.check_output(['git', '-C', str(tree), 'show', revision + ':' + path],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})


def trace_lk(code):
    from audit_gpueb_lk import expect
    require(sha(code) == PINS['lk_payload_sha256'], 'signed B4.1 LK payload mismatch')
    for span, expected in PINS['lk_windows'].items():
        lo, hi = (int(value, 16) for value in span.split('-'))
        require(sha(code[lo:hi]) == expected, 'LK boundary drift: ' + span)
    for check in (
        (0xed58, 'bl', '#0x16eb0'), (0x16eb0, 'mov', 'w0, wzr'), (0x16eb4, 'ret', ''),
        (0xed7c, 'cmn', 'w22, #0x10'), (0xed80, 'b.eq', '#0xed88'),
        (0xed94, 'bl', '#0x1eb88'),
        (0x1eba8, 'mov', 'x24, #0x1eb4'), (0x1ebac, 'movk', 'x24, #0x1c00, lsl #16'),
        (0x1ebc8, 'ldr', 'w8, [x24]'), (0x1ebcc, 'lsr', 'w8, w8, #0x1e'),
        (0x1ebd0, 'cmp', 'w8, #3'), (0x1ebd4, 'b.lo', '#0x1ec04'),
        (0x1ebd8, 'ldr', 'w2, [x24]'), (0x1ebdc, 'tbnz', 'w2, #0xc, #0x1ebf0'),
        (0x1ebe0, 'tbnz', 'w2, #0xd, #0x1ec54'), (0x1ec18, 'mov', 'w22, #-0x10'),
        (0x1ed94, 'bl', '#0x74da0'), (0x1edbc, 'bl', '#0x5e74'),
        (0x1edd4, 'mov', 'w8, #0xf00'), (0x1eddc, 'movk', 'w8, #1, lsl #16'),
        (0x1edf0, 'str', 'w8, [x25]'),
        (0x1ef54, 'mov', 'x8, #0x80c'), (0x1ef5c, 'movk', 'x8, #0x13fa, lsl #16'),
        (0x1ef74, 'ldr', 'w3, [x8]'), (0x1ef78, 'bl', '#0x69c28'),
    ):
        expect(code, *check)
    direct = []
    for offset in range(0x1ec54, 0x1edf4, 4):
        word = struct.unpack_from('<I', code, offset)[0]
        if word >> 26 == 0x25:  # Direct BL immediate, not a CPU execution model.
            displacement = word & 0x3ffffff
            if displacement & 0x2000000:
                displacement -= 0x4000000
            direct.append({'call': hex(offset), 'target': hex(offset + displacement * 4)})
    return {
        'caller': 'LK 0xed58 -> 0x16eb0 (zero-return stub), then 0xed94 -> 0x1eb88',
        'pre_rpc_admission': {'spm': '0x1c001eb4', 'power_ack_bits': '[31:30] == 3',
                              'bit12': 'clear', 'bit13': 'SET, not clear',
                              'success_branch': '0x1ebe0 -> 0x1ec54',
                              'failure': '0x1ec18 returns -16 before allocation/secure firmware loader'},
        'selected_direct_calls_before_rpc': direct,
        'transitive_scope': 'direct call sites only; secure loader/other callees are not declared side-effect-free',
        'rpc_store': {'instruction': '0x1edf0', 'address': '0x13f91030', 'value': '0x10f00'},
        'gpueb_pll_timeout_read': {'address': '0x13fa080c', 'instruction': '0x1ef74',
                                    'meaning': 'read/log after boot timeout, not an initialization producer'},
        'first_unresolved_producer': 'earlier than 0x1ebc8/0x1ebd8: owner/order producing MFG0 ACK and bit13 state',
        'no_inference': 'neither a required MFG0 regulator/basic clock nor an earlier PLL/PMIC programming sequence is established',
    }


def trace_sources(tree):
    data = {}
    for path, expected in PINS['device_sources'].items():
        source = git_source(tree, PINS['device_modules'], path)
        require(sha(source) == expected, 'NOS source mismatch: ' + path)
        data[path] = source.decode()
    domain_path = 'drivers/soc/mediatek/mtk-scpsys-mt6878.c'
    domain = data[domain_path].split('[MT6878_POWER_DOMAIN_MFG0_SHUTDOWN]', 1)[1].split(
        '[MT6878_POWER_DOMAIN_APU]', 1)[0]
    for marker in ('0xEB4', 'GENMASK(8, 8)', 'GENMASK(12, 12)', 'MTK_SCPD_BYPASS_INIT_ON'):
        require(marker in domain, 'NOS MFG0 descriptor drift')
    for marker in ('basic_clk_name', 'basic_lp_clk_name', 'subsys_clk_prefix', 'sram_slp_bits'):
        require(marker not in domain, 'MFG0 cold dependency descriptor changed')
    scpsys = data['drivers/soc/mediatek/mtk-scpsys.c']
    require('if (!scpd->supply)\n\t\treturn 0;' in scpsys and
            'if (PTR_ERR(scpd->supply) == -ENODEV)\n\t\t\t\tscpd->supply = NULL;' in scpsys,
            'NOS optional regulator semantics drift')
    gpu_path = 'drivers/gpu/mediatek/gpufreq/v2/gpufreq_mt6878.c'
    gpu = data[gpu_path]
    require('regulator_get_optional(&pdev->dev, "vgpu")' in gpu and
            'regulator_get_optional(&pdev->dev, "vsram")' in gpu, 'GPUFREQ rail consumer drift')
    for marker in ('regulator_enable(', 'regulator_set_voltage(', 'clk_prepare_enable('):
        require(marker not in gpu, 'MT6878 AP phase changed: ' + marker)
    require('power_control' not in gpu.split('platform_eb_fp = {', 1)[1].split('};', 1)[0],
            'MT6878 AP power callback appeared')
    dt_path = 'arch/arm64/boot/dts/mediatek/mt6878.dts'
    dt = data[dt_path]
    require('vgpu-supply = <&mt6319_6_vbuck2>;' in dt and 'vsram-supply = <&mt6363_vsram_cpum>;' in dt,
            'GPUFREQ DT supply links drift')
    require('compatible = "mediatek,mt6315_6-regulator";' in dt, 'actual MT6319 provider path drift')
    require('&mt6319_6_vbuck2 {\n\tregulator-always-on;' in dt and
            '&mt6363_vsram_cpum {\n\tregulator-always-on;' in dt, 'base DT rail policy drift')
    require('<0 0x13fa0800 0 0x100>' in dt and
            'method = "fhctl-gpueb";\n\t\t\t\tgpueb-ao-gpuebpll' in dt, 'GPUEBPLL FH path drift')
    fh_path = 'drivers/clk/mediatek/clk-fhctl-gpueb.c'
    require('FH_DCTL_CMD_GENERAL_DFS' in data[fh_path] and
            'mtk_ipi_send_compl(get_gpueb_ipidev(), channel_id,' in data[fh_path], 'GPUEBPLL runtime owner drift')
    pll = data['drivers/clk/mediatek/clk-fhctl-pll.c']
    require('DATA_6878_CONVERT("GPUEBPLL")' in pll and
            'REG_6878_TINYSYS_CONVERT(0x14, 0xC)' in pll, 'GPUEBPLL PCW offset drift')
    ccf = data['drivers/clk/mediatek/clk-mt6878.c']
    require('gpueb' not in ccf.lower(), 'native CCF GPUEB provider appeared; reconcile')
    wrapper = data['drivers/gpu/mediatek/gpufreq/v2/gpufreq_v2.c']
    require('gpueb_get_gpr_addr(GPUEB_SRAM_GPR13)' in wrapper and
            'send_msg.cmd_id = CMD_INIT_SHARED_MEM;' in wrapper, 'later GPUFREQ session phase drift')
    regulator = data['drivers/regulator/mt6315-regulator.c']
    require('"mediatek,mt6315_6-regulator"' in regulator and '.enable = mt6315_regulator_enable' in regulator,
            'MT6319 Linux provider implementation drift')
    locations = {
        'native_domain': (domain_path, '[MT6878_POWER_DOMAIN_MFG0_SHUTDOWN]'),
        'optional_regulator': ('drivers/soc/mediatek/mtk-scpsys.c', 'static int scpsys_regulator_enable'),
        'gpu_rail_getters': (gpu_path, 'static int __gpufreq_init_pmic(struct platform_device *pdev)\n{'),
        'gpueb_pll_runtime': (fh_path, 'static int gpueb_hopping_v1'),
        'actual_pmic_provider': ('drivers/regulator/mt6315-regulator.c', 'static int mt6315_regulator_probe'),
    }
    return {'sources': {label: {'path': path, 'line': data[path][:data[path].index(marker)].count('\n') + 1}
                        for label, (path, marker) in locations.items()},
            'mfg0': 'optional absent regulator and no basic clocks; PDN [8]/ACK[12], no MFG0 sleep-bit producer',
            'gpu_rails': 'GPUFREQ get-only in EB mode; VGPU MT6319 USID6 VBUCK2 via mt6315 driver, VSRAM MT6363 CPUM',
            'base_dt_always_on': 'kernel policy only, not an LK-before-RPC cold PMIC write/ownership trace',
            'gpueb_boot_clock': 'gpu1/GPUEBPLL at 0x13fa0800, PCW +0xc; FHCTL uses running GPUEB IPI, not cold initialization',
            'phase_boundary': 'GPUFREQ GPR13 + INIT_SHARED_MEM/POWER_CONTROL is after firmware execution, not a producer for LK entry'}


def trace_modules(tree):
    data = {}
    for path, expected in PINS['module_sources'].items():
        source = git_source(tree, PINS['modules'], path)
        require(sha(source) == expected, 'NOS modules source mismatch: ' + path)
        data[path] = source.decode()
    require(data['gpu/mt6878/mali_avalon'] == '../gpu_mali/mali_avalon/', 'Mali selector symlink drift')
    path = next(name for name in data if name.endswith('.c'))
    source = data[path]
    require('gpufreq_power_control(GPU_PWR_ON)' in source and
            'gpufreq_power_control(GPU_PWR_OFF)' in source, 'Mali power callback drift')
    return {'selection': 'mt6878 -> ../gpu_mali/mali_avalon/, r44p1', 'source': path,
            'power_on_line': source[:source.index('gpufreq_power_control(GPU_PWR_ON)')].count('\n') + 1,
            'phase': 'Mali runtime power callback calls GPUFREQ; not a GPUEB cold boot/PLL producer'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lk', type=Path, required=True)
    parser.add_argument('--device-tree', type=Path, required=True)
    parser.add_argument('--module-tree', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    from audit_gpueb_b41 import signed_lk, read_bounded
    code = signed_lk(read_bounded(args.lk, 8 * 1024 * 1024))
    report = json.dumps({'scope': 'authenticated static boundaries, no hardware or secure permission claim',
                      'pins': {name: PINS[name] for name in ('linux', 'device_modules', 'modules')},
                      'lk': trace_lk(code), 'nos': trace_sources(args.device_tree),
                      'mali_client': trace_modules(args.module_tree)}, indent=2) + '\n'
    if args.report:
        require(args.report.resolve().parent == HERE and args.report.name == 'SOURCE-EVIDENCE.json',
                'generated evidence destination must remain in cold-deps/')
        args.report.write_text(report)
    else:
        print(report, end='')


if __name__ == '__main__':
    main()
