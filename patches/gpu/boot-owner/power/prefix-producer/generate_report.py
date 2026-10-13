#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate a read-only loader observation delta from exact U-Boot git objects."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / 'SOURCE-PINS.json').read_text())
SOURCE = 'board/mediatek/mt6878/mt6878_tetris.c'
MAPPING = 'arch/arm/mach-mediatek/mt6878/init.c'
DEFAULT_TREE = HERE.parents[5] / 'u-boot-mt6878'


def require(value, message):
    if not value:
        raise ValueError(message)


def git_source(tree, revision, path):
    return subprocess.check_output(['git', '-C', str(tree), 'show', revision + ':' + path],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})


def checked_sources(tree):
    result = {}
    for path, expected in PINS['uboot_sources'].items():
        raw = git_source(tree, PINS['uboot_revision'], path)
        require(hashlib.sha256(raw).hexdigest() == expected, 'U-Boot source drift: ' + path)
        result[path] = raw.decode()
    mapping = result[MAPPING].split('/* Peripheral region */', 1)[1].split('},', 1)[0]
    for value in ('.virt = 0x00000000UL', '.phys = 0x00000000UL',
                  '.size = 0x40000000UL', 'MT_DEVICE_NGNRNE'):
        require(value in mapping, 'existing SPM device mapping changed')
    init = result['common/board_r.c']
    sequence = init[init.index('static void initcall_run_r(void)'):]
    require(sequence.index('INITCALL(initr_caches)') < sequence.index('INITCALL(board_late_init)') <
            sequence.index('INITCALL(run_main_loop)'), 'startup observation order changed')
    require('CONFIG_BOARD_LATE_INIT=y' in result['configs/mt6878_tetris_defconfig'], 'startup callback not selected')
    require('#define readl(c)' in result['arch/arm/include/asm/io.h'], 'real MMIO API changed')
    return result


def integrate(source):
    helper = (HERE / 'report.inc').read_text().rstrip() + '\n\n'
    anchor = 'int board_late_init(void)\n'
    require(source.count(anchor) == 1, 'unique startup callback required')
    source = source.replace(anchor, helper + anchor, 1)
    guard = ('#if CONFIG_IS_ENABLED(TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC) || \\\n'
             '\tCONFIG_IS_ENABLED(TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC)\n')
    anchor = '\tif (mode != TETRIS_REBOOT_MODE_BOOTLOADER)\n'
    require(source.count(anchor) == 1, 'unique startup read boundary required')
    source = source.replace(anchor, guard + '\tgpueb_initial_power_capture();\n#endif\n' + anchor, 1)
    anchor = '\tfdt = images->ft_addr;\n\n\tif (IS_ENABLED(CONFIG_TETRIS_SCP_HANDOFF_INVENTORY))'
    require(source.count(anchor) == 1, 'unique bounded pre-SCP/GPU publication boundary required')
    source = source.replace(anchor,
        '#if CONFIG_IS_ENABLED(TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC) || \\\n'
        '\tCONFIG_IS_ENABLED(TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC)\n'
        '\tret = gpueb_initial_report_publish(images);\n'
        '\tif (ret)\n'
        '\t\tprintf("Tetris: GPUEB initial report error=%d (observation only)\\n", ret);\n'
        '#endif\n' + anchor, 1)
    return source


def generated(tree):
    original = checked_sources(tree)[SOURCE]
    return ''.join(difflib.unified_diff(original.splitlines(True),
        integrate(original).splitlines(True), 'a/' + SOURCE, 'b/' + SOURCE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, default=Path(os.environ.get('TETRIS_UBOOT_TREE', DEFAULT_TREE)))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    patch = generated(args.tree)
    target = HERE / 'initial-report.patch'
    if args.check:
        require(target.read_text() == patch, 'initial-report.patch is stale')
    else:
        target.write_text(patch)
    print('Read-only initial report patch checked' if args.check else 'Generated initial-report.patch')


if __name__ == '__main__':
    main()
