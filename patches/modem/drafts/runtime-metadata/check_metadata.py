#!/usr/bin/env python3
"""Exact producer-to-existing-parser candidate; source-only unless GitHub CI."""
import argparse
import difflib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'runtime-object-ci'))
from check_objects import load

PIN = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
PREFIX = 'drivers/misc/mediatek/ccci_util/'
UBOOT_PIN = '60cd9ade5b999732304f3b755c7dbe3d34307c13'


def layout_model(uboot):
    """Retain pinned pure planner/annotation logic; read ONLY copied CHK metadata."""
    extractor = load('metadata_model_extract', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
    def source(name):
        return subprocess.check_output(['git', '-C', str(uboot), 'show',
            f'{UBOOT_PIN}:board/mediatek/mt6878/{name}'], text=True)
    layout = source('tetris_modem_layout.c')
    header = source('tetris_modem_layout.h')
    rows = source('tetris_modem_emi_rows.c')
    structures = []
    for name in ('layout', 'block', 'memory_map', 'smem_entry', 'smem_inputs', 'smem_plan'):
        match = re.search(r'^struct tetris_modem_' + name + r' \{.*?^\};', header, re.M | re.S)
        if not match:
            raise ValueError('pinned layout structure drift: ' + name)
        structures.append(match[0])
    word_matches = list(re.finditer(r'^static unsigned int word\([^;]+?\n\{\n.*?^\}',
                                   layout, re.M | re.S))
    if len(word_matches) != 1:
        raise ValueError('pinned word decoder drift')
    functions = [word_matches[0][0]] + [extractor.function(layout, name)[0] for name in
                 ('contained', 'annotate', 'smem_place', 'tetris_modem_plan_smem_b41')]
    functions[-1] = replace(functions[-1], 'int tetris_modem_plan_smem_b41(',
                            'static int tetris_modem_plan_smem_b41(')
    memory = extractor.function(layout, 'tetris_modem_plan_memory')[0]
    memory = replace(memory,
        'int tetris_modem_plan_memory(const void *rom, size_t rom_size, size_t dsp_size,',
        'static int tetris_metadata_memory(const unsigned char *chk, size_t rom_size,')
    memory = replace(memory,
        '\tret = tetris_modem_plan_layout(rom, rom_size, dsp_size, capacity, &layout);\n'
        '\tif (ret)\n\t\treturn ret;\n'
        '\theader = (const unsigned char *)rom + rom_size - CHECK_SIZE;',
        '\t/* Caller checked the fixed CHK and all region bounds. No ROM read. */\n'
        '\tmemset(&layout, 0, sizeof(layout));\n'
        '\tlayout.memory_size = word(chk + 172);\n'
        '\tlayout.dsp_offset = word(chk + 184);\n'
        '\tlayout.dsp_capacity = word(chk + 188);\n'
        '\tlayout.region_count = word(chk + 192);\n\theader = chk;')
    functions.extend((memory, extractor.function(rows, 'padding')[0]))
    return ('/* SPDX-License-Identifier: GPL-2.0+ */\n'
        f'/* Generated pure layout logic from U-Boot {UBOOT_PIN}. */\n'
        '#ifndef TETRIS_METADATA_LAYOUT_MODEL_H\n#define TETRIS_METADATA_LAYOUT_MODEL_H\n'
        '#define TETRIS_MODEM_MAX_BLOCKS 32\n\n' + '\n\n'.join(structures + functions) +
        '\n#endif\n')


def stock(vendor, name):
    return subprocess.check_output(['git', '-C', str(vendor), 'show',
        f'{PIN}:{PREFIX}{name}'], text=True)


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('source drift: ' + old[:80])
    return source.replace(old, new, 1)


def build(vendor):
    before = {PREFIX + name: stock(vendor, name) for name in
        ('ccci_util_boot_args.c', 'ccci_util_lib_fo.c', 'ccci_util_lib_main.h',
         'ccci_util_lib_main.c')}
    dependency_path = 'drivers/misc/mediatek/eccci/fsm/ccci_tetris_dependencies.h'
    before[dependency_path] = (HERE.parent / 'runtime-ports/ccci_tetris_dependencies.h').read_text()
    after = dict(before)
    after[dependency_path] = replace(after[dependency_path],
        'static int tetris_ccci_descriptor(struct device_node *node)',
        '/* Owned metadata admission is supplied by ccci_util, before HIF links. */\n'
        'extern int mtk_ccci_validate_owned_handoff(struct device_node *);\n\n'
        'static int tetris_ccci_descriptor(struct device_node *node)')
    after[dependency_path] = replace(after[dependency_path],
        '\tret = tetris_ccci_descriptor(consumer->dev.of_node);',
        '\tret = mtk_ccci_validate_owned_handoff(consumer->dev.of_node);\n'
        '\tif (ret)\n\t\treturn ret;\n'
        '\tret = tetris_ccci_descriptor(consumer->dev.of_node);')
    path = PREFIX + 'ccci_util_boot_args.c'
    after[path] = replace(after[path], '#include <linux/of_fdt.h>',
        '#include <linux/of_fdt.h>\n#include <linux/unaligned.h>')
    after[path] = replace(after[path], 'int mtk_ccci_add_new_args(',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n#include "owned_tags.h"\n#endif\n\n'
        'int mtk_ccci_add_new_args(')
    path = PREFIX + 'ccci_util_lib_main.h'
    after[path] = replace(after[path], '#define MAX_MD_NUM_AT_LK\t(4)',
        '/* AP-owned coherent tag mapping; no firmware/auth/access grant. */\n'
        '#include "metadata_resources.h"\n'
        'int mtk_ccci_import_owned_tags(const void __iomem *, unsigned int,\n'
        '\t\tunsigned int, unsigned int, const struct tetris_metadata_banks *);\n'
        'struct device_node;\n'
        'int mtk_ccci_validate_owned_handoff(struct device_node *);\n\n'
        '#define MAX_MD_NUM_AT_LK\t(4)')
    path = PREFIX + 'ccci_util_lib_fo.c'
    after[path] = replace(after[path], 'static int __init collect_lk_boot_arguments(void)',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '#include "handoff.h"\n#endif\n\n'
        'static int __init collect_lk_boot_arguments(void)')
    after[path] = replace(after[path], '\traw_ptr = (unsigned int *)of_get_property(node, "ccci,modem_info_v2",',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\t/* Metadata-only: bypass legacy parser and its protected SMEM maps. */\n'
        '\tret = tetris_collect_owned_metadata(node);\n'
        '\tof_node_put(node);\n\treturn ret;\n#endif\n\n'
        '\traw_ptr = (unsigned int *)of_get_property(node, "ccci,modem_info_v2",')
    after[path] = replace(after[path], '//\tint ret;\n\tunsigned int *raw_ptr;',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n\tint ret;\n#endif\n'
        '\tunsigned int *raw_ptr;')
    after[path] = replace(after[path], '\tlk_tag_inf_parsing_to_args_table();',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tret = lk_tag_inf_parsing_to_args_table();\n\tif (ret)\n\t\treturn ret;\n'
        '#else\n\tlk_tag_inf_parsing_to_args_table();\n#endif')
    after[path] = replace(after[path], '\tmtk_ccci_md_smem_layout_init();',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tret = mtk_ccci_md_smem_layout_init();\n\tif (ret)\n\t\treturn ret;\n'
        '#else\n\tmtk_ccci_md_smem_layout_init();\n#endif')
    after[path] = replace(after[path], '\tif (collect_lk_boot_arguments() == 0) {',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\t/* Do not turn failed owned metadata import into legacy success. */\n'
        '\treturn collect_lk_boot_arguments();\n#endif\n\n'
        '\tif (collect_lk_boot_arguments() == 0) {')
    path = PREFIX + 'ccci_util_lib_main.c'
    after[path] = replace(after[path], '\tccci_log_init();\n\tmtk_ccci_args_key_val_init();\n\tccci_util_fo_init();',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n\tint ret;\n#endif\n'
        '\tccci_log_init();\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tret = mtk_ccci_args_key_val_init();\n\tif (ret)\n\t\treturn ret;\n'
        '\tret = ccci_util_fo_init();\n\tif (ret)\n\t\treturn ret;\n'
        '#else\n\tmtk_ccci_args_key_val_init();\n\tccci_util_fo_init();\n#endif')
    # Owned mode returns before the legacy path: never map/clear protected SMEM.
    after[PREFIX + 'owned_tags.h'] = (HERE / 'owned_tags.h').read_text()
    after[PREFIX + 'handoff.h'] = (HERE / 'handoff.h').read_text()
    for name in ('metadata_resources.h', 'layout_model.h', 'semantic.h'):
        after[PREFIX + name] = (HERE / name).read_text()
    result = []
    for path in sorted(after):
        new = after[path]
        old = before.get(path, '')
        if old == new:
            continue
        result.append(f'diff --git a/{path} b/{path}\n')
        if not old:
            result.append('new file mode 100644\n')
        result.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='a/' + path if old else '/dev/null', tofile='b/' + path))
    return ''.join(result), before


def native_fixture_sources(vendor):
    """Materialize exact fixture code for source checks without any compiler."""
    lifecycle = load('metadata_function_extract', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
    args = stock(vendor, 'ccci_util_boot_args.c')
    structure = re.search(r'^struct args_key_val \{.*?^\};', args, re.M | re.S)
    if not structure:
        raise ValueError('pinned args structure drift')
    lookup = '\n\n'.join(lifecycle.function(args, name)[0] for name in
                         ('is_key_exist', 'mtk_ccci_find_args_val'))
    fixture = (HERE / 'test_import.c').read_text().replace('/* STRUCT */', structure[0])
    fixture = fixture.replace('/* EXISTING_LOOKUP */', lookup)
    fixture = fixture.replace('/* IMPORT */', (HERE / 'owned_tags.h').read_text())
    producer_test = (HERE.parent / 'boot-producers/test_ccci_tags.c').read_text()
    producer_test = replace(producer_test, 'which = atoi(argv[2]);', 'which = 0;')
    producer_test = ('#include "metadata_resources.h"\n'
        'void kernel_import_probe(unsigned char *, unsigned int, unsigned int, '
        'const struct tetris_metadata_banks *);\n' + producer_test)
    # Same signed stock, different synthetic owned allocations: no universal bases.
    for field, first, second in (('firmware', '0x80000000ULL', '0x100000000ULL'),
                                 ('nc', '0xa0000000ULL', '0x120000000ULL'),
                                 ('cache', '0xc0000000ULL', '0x140000000ULL')):
        producer_test = replace(producer_test, f'.{field} = {{ {first},',
            f'.{field} = {{ atoi(argv[2]) == 58 ? {second} : {first},')
    producer_test = replace(producer_test, '.dram_size = 0x100000000ULL,',
        '.dram_size = atoi(argv[2]) == 58 ? 0x200000000ULL : 0x100000000ULL,')
    position = producer_test.rfind('\treturn 0;')
    if position < 0:
        raise ValueError('producer fixture return drift')
    producer_test = (producer_test[:position] +
        '\tconst struct tetris_metadata_banks banks = {\n'
        '\t\t.firmware = { report.bootstrap.resources.firmware.base, report.bootstrap.resources.firmware.capacity },\n'
        '\t\t.nc = { report.bootstrap.resources.nc.base, report.bootstrap.resources.nc.capacity },\n'
        '\t\t.cache = { report.bootstrap.resources.cache.base, report.bootstrap.resources.cache.capacity },\n'
        '\t\t.tags = { 0x180000000ULL, 65536 }, /* synthetic AP buffer */\n\t};\n'
        '\tkernel_import_probe(buffer, (unsigned int)ret, (unsigned int)atoi(argv[2]), &banks);\n' +
        producer_test[position:])
    return fixture, producer_test


def native_ci(vendor, uboot, stock_container):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('native C is GitHub CI-only')
    lifecycle = load('metadata_ci_function_extract', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
    fixture, producer_test = native_fixture_sources(vendor)
    with tempfile.TemporaryDirectory(prefix='metadata-native-') as temp:
        root = Path(temp)
        names = ('tetris_modem_layout.c', 'tetris_modem_layout.h', 'tetris_modem_bundle.h',
                 'tetris_modem_emi.c', 'tetris_modem_emi.h', 'tetris_modem_remap.h',
                 'tetris_modem_emi_rows.c', 'tetris_modem_emi_rows.h',
                 'tetris_modem_ccci_tags.c', 'tetris_modem_ccci_tags.h',
                 'tetris_modem_loaded_boot.h', 'tetris_modem_bootstrap.h',
                 'tetris_modem_boot_secure.h')
        for name in names:
            (root / name).write_bytes(subprocess.check_output(['git', '-C', str(uboot),
                'show', f'{UBOOT_PIN}:board/mediatek/mt6878/{name}']))
        (root / 'linux').mkdir()
        (root / 'linux/errno.h').write_text('#include <asm-generic/errno.h>\n')
        (root / 'linux/string.h').write_text('#include <string.h>\n')
        (root / 'import.c').write_text(fixture)
        for name in ('metadata_resources.h', 'layout_model.h', 'semantic.h'):
            (root / name).write_bytes((HERE / name).read_bytes())
        (root / 'producer_test.c').write_text(producer_test)
        binary = root / 'roundtrip'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-O1', '-g',
            '-DTETRIS_MODEM_LAYOUT_HOST_TEST', '-I', str(root),
            *(str(root / name) for name in ('tetris_modem_layout.c', 'tetris_modem_emi.c',
              'tetris_modem_emi_rows.c', 'tetris_modem_ccci_tags.c', 'import.c',
              'producer_test.c')), '-o', str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1')
        for case in range(59):
            subprocess.run([str(binary), str(stock_container), str(case)], env=env, check=True)
        decoders = '\n\n'.join(lifecycle.function((HERE / 'handoff.h').read_text(), name)[0]
                               for name in ('tetris_brom_result', 'tetris_descriptor_bytes'))
        (root / 'test_handoff.c').write_text((HERE / 'test_handoff.c').read_text().replace(
            '/* DECODERS */', decoders))
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-O1', '-g',
            str(root / 'test_handoff.c'), '-o', str(root / 'handoff')], check=True)
        subprocess.run([str(root / 'handoff')], env=env, check=True)
        handoff = (HERE / 'handoff.h').read_text()
        structure = re.search(r'^struct tetris_nomap_cover \{.*?^\};', handoff, re.M | re.S)
        if not structure:
            raise ValueError('retained NOMAP coverage structure drift')
        adapter = structure[0] + '\n\n' + '\n\n'.join(lifecycle.function(handoff, name)[0]
            for name in ('tetris_nomap_resource', 'tetris_retained_nomap', 'tetris_owned_banks'))
        (root / 'test_reservations.c').write_text((HERE / 'test_reservations.c').read_text().replace(
            '/* OF_ADAPTER */', adapter))
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-O1', '-g',
            '-I', str(root), str(root / 'test_reservations.c'),
            '-o', str(root / 'reservations')], check=True)
        subprocess.run([str(root / 'reservations')], env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--emit-patch', type=Path)
    parser.add_argument('--native-ci', action='store_true')
    parser.add_argument('--uboot', type=Path)
    parser.add_argument('--stock-container', type=Path)
    parser.add_argument('--emit-model', action='store_true')
    args = parser.parse_args()
    if args.uboot:
        model = layout_model(args.uboot)
        if args.emit_model:
            (HERE / 'layout_model.h').write_text(model)
        if model != (HERE / 'layout_model.h').read_text():
            raise ValueError('pinned layout model drift')
    elif args.emit_model:
        parser.error('--emit-model requires --uboot')
    patch, before = build(args.vendor)
    if args.emit_patch:
        args.emit_patch.write_text(patch)
    if patch != (HERE / 'runtime-metadata.patch.vendor').read_text():
        raise ValueError('review overlay differs from generated source')
    with tempfile.TemporaryDirectory(prefix='metadata-apply-') as temp:
        root = Path(temp)
        for name, content in before.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        subprocess.run(['git', 'apply', '--check', '-'], input=patch,
                       text=True, cwd=root, check=True)
    print('Metadata producer/parser source and patch apply PASS; no mapping or activation')
    if args.native_ci:
        if not args.uboot or not args.stock_container:
            parser.error('--native-ci requires --uboot and --stock-container')
        native_ci(args.vendor, args.uboot, args.stock_container)


if __name__ == '__main__':
    main()
