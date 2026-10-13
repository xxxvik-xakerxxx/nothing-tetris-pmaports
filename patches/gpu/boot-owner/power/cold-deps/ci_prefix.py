#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Isolated CI native-MFG0 prefix objects, not the frozen full-power variant."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from generate_prefix import HERE, ROOT, PINS, NATIVE, RESEARCH, native_variant, render
sys.path.insert(0, str(HERE.parents[1]))
import ci_join as join

UNITS = ('mt6878-gpueb-mfg0', 'mt6878-gpueb-sram', 'mt6878-gpueb-sram-core',
         'mt6878-gpueb-reset', 'mtk-pm-domains', 'mt6878-gpueb-cold-prefix')
SYMBOLS = ('mt6878_gpueb_cold_prefix_prepare', 'mt6878_cold_mfg0_preflight',
           'mt6878_cold_mfg0_readback', 'mt6878_gpueb_mfg0_resume',
           'mt6878_gpueb_sram_create', 'mt6878_gpueb_reset_validate_resources')


def checked_sources():
    patch, sources = render()
    join.require((HERE / 'native-prefix.patch').read_text() == patch, 'prefix delta stale')
    return {path if path.startswith('include/') else Path(path).name: text for path, text in sources.items()}


def prepared_inputs(kernel, output, baseline):
    # Read-only canonical/root provenance checks; stage ORIGINAL SRAM/reset
    # owners, not their upload join. No flat loan or full-power caller is linked.
    _, fingerprints = join.prepared_inputs(kernel, output, baseline)
    manifest = json.loads(baseline.read_text())
    files = checked_sources()
    for stem in ('mt6878-gpueb-sram', 'mt6878-gpueb-sram-core', 'mt6878-gpueb-reset'):
        for suffix in ('.c', '.h'):
            path = RESEARCH + stem + suffix
            files[stem + suffix] = (kernel / path).read_text()
    for name, expected in (('mt6878-gpueb-mfg0.c', PINS['mfg0_source_sha256']),
                           ('mt6878-gpueb-mfg0.h', PINS['mfg0_header_sha256'])):
        origin = 'patches/gpu/mfg0-supplier-draft/' + name
        join.require(manifest.get('research_source_sha256', {}).get(origin) == expected,
                     'baseline lacks original MFG0 supplier')
        join.require(join.sha(kernel / (RESEARCH + name)) == expected, 'prepared MFG0 drift')
        fingerprints[RESEARCH + name] = expected
    files['mtk-pm-domains.c'] = native_variant((kernel / NATIVE).read_text())
    fingerprints[NATIVE] = PINS['native_prepared_sha256']
    for path, expected in PINS['native_headers'].items():
        join.require(join.sha(kernel / path) == expected, 'native MFG0 descriptor/header drift: ' + path)
    for path in (kernel / NATIVE).parent.glob('*.h'):
        join.require(not path.is_symlink() and path.name not in files, 'unsafe/colliding native header')
        files[path.name] = path.read_text()
        fingerprints[str(path.relative_to(kernel))] = join.sha(path)
    for setting in ('CONFIG_PM=y', 'CONFIG_PM_GENERIC_DOMAINS=y', 'CONFIG_MTK_PM_DOMAINS=y'):
        join.require(setting in (output / '.config').read_text().splitlines(), 'prefix config missing: ' + setting)
    return files, fingerprints


def stage(kernel, output, work, baseline):
    files, fingerprints = prepared_inputs(kernel, output, baseline)
    work.mkdir(parents=True, exist_ok=False)
    variant = work / 'source'
    variant.mkdir()
    for name, source in files.items():
        target = variant / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    (variant / 'Makefile').write_text('ccflags-y += -I$(src)/include\nobj-y += ' +
                                    ' '.join(unit + '.o' for unit in UNITS) + '\n')
    shutil.copytree(output, work / 'output', symlinks=True)
    return variant, fingerprints


def kernel_command(kernel, output, variant):
    return ['make', '-C', kernel, 'O=' + str(output.resolve()), 'M=' + str(variant.resolve()),
            'ARCH=arm64', 'LLVM=1', '-j4', 'KCFLAGS=-Werror', *(unit + '.o' for unit in UNITS)]


def build(kernel, output, work, report, baseline):
    join.require(os.environ.get('CI') == 'true' and os.environ.get('GITHUB_ACTIONS') == 'true',
                 'prefix compilation is CI-only')
    join.disjoint(work, report, kernel, output)
    report.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'started', 'linux': PINS['linux'], 'pmaports': os.environ.get('GITHUB_SHA'),
                'scope': 'native MFG0 prefix objects/internal link only; no mock dependencies, '
                         'RPC/PLL/PMIC activation, physical-state proof, final link or modpost'}
    try:
        variant, inputs = stage(kernel, output, work, baseline)
        manifest['inputs'] = inputs
        compiler = subprocess.check_output(['clang', '--version'], text=True)
        join.require(re.search(r'clang version 21\.', compiler), 'parent-matching clang21 required')
        manifest['compiler'] = compiler.strip()
        manifest['sources'] = {str(path.relative_to(variant)): join.sha(path)
                               for path in variant.rglob('*') if path.is_file()}
        command = kernel_command(kernel, work / 'output', variant)
        manifest['kernel_command'] = list(map(str, command))
        join.run(command)
        objects = [variant / (unit + '.o') for unit in UNITS]
        manifest['objects'] = {path.name: {**join.object_identity(path), 'sha256': join.sha(path)}
                               for path in objects}
        formats = {row['format'] for row in manifest['objects'].values()}
        join.require(len(formats) == 1, 'mixed native object formats')
        linked = variant / 'cold-prefix.o'
        join.run(['llvm-link', '-o', linked, *objects] if formats == {'LLVM bitcode'} else
                 ['ld.lld', '-r', '-o', linked, *objects])
        defined = subprocess.check_output(['llvm-nm', '--defined-only', str(linked)], text=True)
        undefined = subprocess.check_output(['llvm-nm', '-u', str(linked)], text=True)
        symbols = {row.split()[-1] for row in defined.splitlines() if row.split()}
        raw = {row.split()[-1] for row in undefined.splitlines() if row.split()}
        remaining = sorted(raw - symbols)  # Exact definitions resolve LLVM export assembly.
        manifest.update(raw_undefined=sorted(raw), unverified_kernel_imports=remaining)
        for path in [*objects, linked]:
            shutil.copyfile(path, report / path.name)
        join.require(set(SYMBOLS) <= symbols, 'actual prefix API definition missing')
        join.require(not any(name.startswith(('mt6878_gpueb_', 'mt6878_cold_mfg0_', 'gpueb_sram_'))
                             for name in remaining), 'unresolved internal prefix owner dependency')
        for path, expected in inputs.items():
            source = output / path if path in ('.config', 'include/generated/autoconf.h',
                                              'include/config/auto.conf') else kernel / path
            join.require(join.sha(source) == expected, 'shared source/config changed: ' + path)
        shutil.copyfile(work / 'output/.config', report / 'config')
        manifest['status'] = 'passed'
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        raise
    finally:
        (report / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'out/kernel-object-smoke/BUILD-MANIFEST.json')
    parser.add_argument('--work', type=Path, default=Path('/tmp/tetris-cold-mfg0-prefix'))
    parser.add_argument('--report', type=Path, default=ROOT / 'out/kernel-object-smoke/cold-mfg0-prefix')
    args = parser.parse_args()
    if args.check:
        print(json.dumps({'source_checks': 'passed', 'sources': sorted(checked_sources()),
                          'units': UNITS, 'api': SYMBOLS, 'activation': 'none'}, indent=2))
    else:
        if not args.kernel or not args.output:
            parser.error('--kernel and --output from the passed research-owner build required')
        build(args.kernel.resolve(), args.output.resolve(), args.work.resolve(), args.report.resolve(), args.baseline)
