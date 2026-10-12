#!/usr/bin/env python3
"""Run real provider/private-export/consumer bodies with kernel boundary mocks."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
from check_consumer import HERE, ECCCI, build, load, replace


def function(source, name):
    found = re.findall(r'^(?:static )?(?:bool|int) ' + re.escape(name) +
                       r'\([^;]+?\n\{\n.*?^\}', source, re.M | re.S)
    if len(found) != 1:
        raise ValueError('actual private-export source drift: ' + name)
    return found[0]


def prepare_fixture(vendor):
    """Source assembly only; callable by local checks without a C compiler."""
    original = (HERE.parent / 'runtime-prepare/test_registration.c').read_text()
    boundary = original.split('/* PRODUCTION */', 1)[0]
    boundary = replace(boundary, '#include <stdlib.h>\n',
        '#include <stdlib.h>\n#include <string.h>\n#define __iomem\n#define GFP_KERNEL 0\n'
        'typedef uint64_t phys_addr_t;\n#include "ap_md_mem.h"\n'
        '#include "mt-plat/tetris_ccci_smem.h"\n')
    boundary = replace(boundary, '#define IS_ENABLED(config) 0', '#define IS_ENABLED(config) (config)')
    boundary = replace(boundary, 'struct ccci_modem {\n',
        'struct ccci_modem {\n\tstruct ccci_mem_layout mem_layout;\n'
        '\tstruct tetris_ccci_smem_copy *tetris_smem;\n')
    boundary = replace(boundary,
        'static int md_init(struct ccci_modem *md) { assert(md); return fault == 7 ? -EIO : 0; }',
        'static int md_init(struct ccci_modem *md) { assert(md && md->tetris_smem); '
        'assert(md->mem_layout.md_bank4_noncacheable == md->tetris_smem->nc); '
        'return fault == 7 ? -EIO : 0; }')
    boundary = replace(boundary, ', exposed_fault;', ';')
    registration = build(vendor)['consumer.overlay'][2][ECCCI + 'fsm/register_prepare.h']
    registration = '\n'.join(line for line in registration.splitlines()
                             if not line.startswith('#include '))
    return boundary + replace((HERE / 'test_prepare.c').read_text(),
                              '/* ACTUAL_REGISTRATION */', registration)


def run(vendor):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('native C compilation/execution is GitHub CI-only')
    smem = load('consumer_native_types', HERE.parent / 'runtime-smem/check_smem.py')
    original = (HERE.parent / 'runtime-smem/smem.c').read_text()
    bodies = '\n\n'.join(function(original, name) for name in
        ('output_overlap', 'copy_layout', 'tetris_smem_export_mapped_private'))
    source = (HERE / 'test_binding.c').read_text().replace('/* REAL_EXPORT */', bodies)
    with tempfile.TemporaryDirectory(prefix='tetris-smem-binding-native-') as temp:
        root = Path(temp)
        for name in ('provider.h', 'consumer.h'):
            (root / name).write_bytes((HERE / name).read_bytes())
        for name in ('private.h', 'smem.h'):
            (root / name).write_bytes((HERE.parent / 'runtime-smem' / name).read_bytes())
        (root / 'metadata_resources.h').write_bytes(
            (HERE.parent / 'runtime-metadata/metadata_resources.h').read_bytes())
        (root / 'ap_md_mem.h').write_text(smem.native_types(vendor))
        for relative in ('linux/mutex.h', 'linux/module.h', 'linux/slab.h', 'linux/string.h'):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('/* Native kernel boundary supplied by test_binding.c. */\n')
        interface = root / 'mt-plat/tetris_ccci_smem.h'
        interface.parent.mkdir()
        interface.write_bytes((HERE / 'tetris_ccci_smem.h').read_bytes())
        unit = root / 'binding.c'
        unit.write_text(source)
        flags = ['-DMODULE=1', '-DCONFIG_MTK_ECCCI_TETRIS_OWNER=1',
                 '-DCONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY=1',
                 '-DCONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1',
                 '-DCONFIG_TETRIS_CCCI_SMEM_PROVIDER=1',
                 '-DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1']
        binary = root / 'binding'
        command = [os.environ.get('CC', 'clang'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
                   '-fno-omit-frame-pointer', '-I', str(root)]
        subprocess.run([*command, *flags, str(unit), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, env=dict(os.environ,
            ASAN_OPTIONS='detect_leaks=1:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
        # Reuse the existing real registration kernel boundaries, not its old
        # publication tests. Execute the new actual transaction with memory faults.
        preparation = root / 'prepare.c'
        preparation.write_text(prepare_fixture(vendor))
        prepared_binary = root / 'prepare'
        subprocess.run([*command, *flags, str(preparation), '-o', str(prepared_binary)], check=True)
        subprocess.run([str(prepared_binary)], check=True, env=dict(os.environ,
            ASAN_OPTIONS='detect_leaks=1:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
        for macro, diagnostic in (
                ('CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY', 'checked MAP_ONLY profile'),
                ('CONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY', 'isolated AP-only util'),
                ('CONFIG_MTK_ECCCI_TETRIS_OWNER', 'unpublished OWNER prepare transaction')):
            rejected = subprocess.run([*command, *[item for item in flags if item != '-D' + macro + '=1'],
                '-D' + macro + '=0', '-c', str(unit), '-o', str(root / 'invalid.o')],
                text=True, capture_output=True)
            if not rejected.returncode or diagnostic not in rejected.stderr:
                raise ValueError('invalid provider/consumer compile profile accepted: ' + macro)
        rejected = subprocess.run([*command, *[item for item in flags if item != '-DMODULE=1'],
            '-c', str(unit), '-o', str(root / 'builtin-invalid.o')], text=True, capture_output=True)
        if not rejected.returncode or 'loadable module lifetime' not in rejected.stderr:
            raise ValueError('builtin provider without module lifetime accepted')
    print('Actual provider/private export/consumer native sanitized binding PASS; no mapping or hardware')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    run(parser.parse_args().vendor)
