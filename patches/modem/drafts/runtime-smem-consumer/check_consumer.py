#!/usr/bin/env python3
"""Generate additive checked SMEM provider/consumer overlays; source-only locally."""
import argparse
import difflib
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PIN = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
ECCCI = 'drivers/misc/mediatek/eccci/'
UTIL = 'drivers/misc/mediatek/ccci_util/'
COMMON = 'drivers/misc/mediatek/include/mt-plat/tetris_ccci_smem.h'
GUARD = '#if defined(CONFIG_TETRIS_CCCI_SMEM_CONSUMER) && CONFIG_TETRIS_CCCI_SMEM_CONSUMER\n'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('exact SMEM consumer source drift: ' + repr(old[:100]))
    return source.replace(old, new, 1)


def patch(before, after):
    chunks = []
    for name, new in sorted(after.items()):
        old = before.get(name, '')
        if new == old:
            continue
        chunks.append(f'diff --git a/{name} b/{name}\n')
        if not old:
            chunks.append('new file mode 100644\n')
        chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='a/' + name if old else '/dev/null', tofile='b/' + name))
    return ''.join(chunks)


def consumer_sources(before):
    after = dict(before)
    header = ECCCI + 'modem_sys.h'
    after[header] = replace(after[header], 'struct ccci_modem {\n',
        'struct tetris_ccci_smem_copy;\n\nstruct ccci_modem {\n')
    after[header] = replace(after[header], '\tvoid *ioremap_buff_src;\n};',
        '\tvoid *ioremap_buff_src;\n' + GUARD +
        '#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '#error "Tetris SMEM consumer requires OWNER layout lifetime"\n#endif\n'
        '\tstruct tetris_ccci_smem_copy *tetris_smem;\n#endif\n};')
    main = ECCCI + 'fsm/modem_sys1.c'
    after[main] = replace(after[main], '#include "register_prepare.h"',
        '#include "tetris_smem_consumer.h"\n#include "register_prepare.h"')
    after[main] = replace(after[main], 'void ccci_md_config(struct ccci_modem *md)\n{\n',
        'void ccci_md_config(struct ccci_modem *md)\n{\n' + GUARD +
        '\t/* Checked private preparation already owns memory. Legacy void\n'
        '\t * config cannot replace it or consume unpublished util globals. */\n'
        '\t(void)md;\n\treturn;\n#endif\n')
    registration = ECCCI + 'fsm/register_prepare.h'
    after[registration] = replace(after[registration], '\tret = ccci_tetris_fsm_prepare();',
        GUARD + '\tret = tetris_ccci_mem_prepare(md);\n'
        '\tif (ret)\n\t\tgoto free_peer;\n#endif\n'
        '\tret = ccci_tetris_fsm_prepare();')
    after[registration] = replace(after[registration], 'free_peer:\n',
        'free_peer:\n' + GUARD + '\ttetris_ccci_mem_abort(md);\n#endif\n')
    after[registration] = replace(after[registration],
        '\tint ret;\n\n\tif (!pdev)\n', '\tint ret;\n\n' + GUARD +
        '\t/* Memory preparation alone does not own operational dependencies. */\n'
        '\treturn -EOPNOTSUPP;\n#endif\n\tif (!pdev)\n')
    after[ECCCI + 'fsm/tetris_smem_consumer.h'] = (HERE / 'consumer.h').read_text()
    return after


def build(vendor):
    staging = load('smem_consumer_staging', HERE.parent / 'runtime-object-ci/check_objects.py')
    for name in ('runtime-smem', 'runtime-metadata', 'runtime-prepare', 'runtime-lifecycle'):
        staging.review(HERE.parent / name)
    prepare = load('smem_consumer_prepare', HERE.parent / 'runtime-prepare/check_prepare.py')
    generated, _, prepared = prepare.build(vendor)
    if generated != (HERE.parent / 'runtime-prepare/runtime-prepare.patch.vendor').read_text():
        raise ValueError('prepare source differs from frozen overlay')
    lifecycle = load('smem_consumer_lifecycle', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
    lifecycle_patch, old, new = lifecycle.build(vendor)
    if lifecycle_patch != (HERE.parent / 'runtime-lifecycle/runtime-lifecycle.patch.vendor').read_text():
        raise ValueError('lifecycle source differs from frozen overlay')
    if prepared[lifecycle.SOURCE] != old:
        raise ValueError('prepare/lifecycle source chain mismatch')
    names = (ECCCI + 'fsm/modem_sys1.c', ECCCI + 'fsm/register_prepare.h')
    consumer_before = {name: prepared[name] for name in names}
    consumer_before[lifecycle.SOURCE] = new
    consumer_before[ECCCI + 'modem_sys.h'] = subprocess.check_output(
        ['git', '-C', str(vendor), 'show', PIN + ':' + ECCCI + 'modem_sys.h'], text=True)
    consumer_after = consumer_sources(consumer_before)
    package = load('smem_consumer_package', HERE.parent / 'runtime-metadata/package_metadata.py')
    packaged, files = package.build(vendor)
    if packaged != (HERE.parent / 'runtime-metadata/ccci-owned-metadata.overlay').read_text():
        raise ValueError('AP-only source differs from frozen packaged overlay')
    provider_before = {UTIL + 'owned_smem_plan.c': files[UTIL + 'owned_smem_plan.c']}
    provider_after = {
        UTIL + 'owned_smem_plan.c': provider_before[UTIL + 'owned_smem_plan.c'] +
            '\n#include "tetris_smem_provider.h"\n',
        UTIL + 'tetris_smem_provider.h': (HERE / 'provider.h').read_text(),
    }
    bundles = {
        'common.overlay': ({}, {COMMON: (HERE / 'tetris_ccci_smem.h').read_text()}),
        'provider.overlay': (provider_before, provider_after),
        'consumer.overlay': (consumer_before, consumer_after),
    }
    return {name: (patch(before, after), before, after)
            for name, (before, after) in bundles.items()}


def apply_check(text, before):
    with tempfile.TemporaryDirectory(prefix='tetris-smem-consumer-apply-') as temp:
        root = Path(temp)
        for name, source in before.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
        subprocess.run(['git', 'apply', '--check', '-'], cwd=root,
                       input=text, text=True, check=True, capture_output=True)
        subprocess.run(['git', 'apply', '-'], cwd=root,
                       input=text, text=True, check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--emit', action='store_true')
    args = parser.parse_args()
    bundles = build(args.vendor)
    for name, (text, before, _) in bundles.items():
        if args.emit:
            (HERE / name).write_text(text)
        if (HERE / name).read_text() != text:
            raise ValueError('frozen additive overlay mismatch: ' + name)
        apply_check(text, before)
    if args.emit:
        names = sorted(path.name for path in HERE.iterdir() if path.is_file()
                       and (path.name == 'Kbuild' or path.suffix in ('.py', '.c', '.h', '.overlay', '.md')))
        (HERE / 'REVIEW.sha256').write_text(''.join(
            f'{hashlib.sha256((HERE / name).read_bytes()).hexdigest()}  {name}\n'
            for name in names))
    print('Source-only complete prepare/lifecycle + isolated AP provider overlays PASS')


if __name__ == '__main__':
    main()
