#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""CI-only private DRAM object/native faults; no shipping caller or GPR write."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ci_join

PINS = json.loads((HERE / 'SOURCE-PINS.json').read_text())
NAMES = ('mt6878-gpueb-dram.c', 'mt6878-gpueb-dram.h', 'dram-host.h', 'test-dram.c')
UNIT = 'mt6878-gpueb-dram'
API = ('mt6878_gpueb_dram_create', 'mt6878_gpueb_dram_acquire',
       'mt6878_gpueb_dram_candidate_gpr6', 'mt6878_gpueb_dram_put', 'mt6878_gpueb_dram_destroy')


def blob_id(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def source_check():
    ci_join.checked_sources()
    source = (HERE / NAMES[0]).read_text()
    for name in API:
        ci_join.require(name in source and name in (HERE / NAMES[1]).read_text(), 'missing DRAM API: ' + name)
    for operation in ('cma_alloc(dram->area, GPUEB_DRAM_PAGES, alignment, false)',
                      'cma_release(dram->area, dram->pages, GPUEB_DRAM_PAGES)',
                      'dram->physical = page_to_phys(dram->pages)', '*word = dram->physical >> 12',
                      'if (dram->loan)', 'ret = -EBUSY;'):
        ci_join.require(operation in source, 'missing real allocator/loan operation: ' + operation)
    # Examine code, not explanatory comments.
    code = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    ci_join.require(not re.search(r'\b(?:writel|readl|ioremap|memset|memcpy|arm_smccc_smc|'
                                  r'pm_runtime_resume_and_get|EXPORT_SYMBOL|module_init)\b', code),
                    'unexpected hardware/data publication or module installation')
    return {name: ci_join.sha(HERE / name) for name in NAMES}


def validate_kernel(kernel, output):
    for path, digest in PINS['linux_blobs'].items():
        ci_join.require(blob_id((kernel / path).read_bytes()) == digest, 'pinned Linux allocator/API drift: ' + path)
    config = (output / '.config').read_text().splitlines()
    for option in ('CONFIG_CMA=y', 'CONFIG_DMA_CMA=y'):
        ci_join.require(option in config, 'real DRAM allocation dependency missing: ' + option)


def stage(kernel, output, work, baseline):
    validate_kernel(kernel, output)
    digests = source_check()
    variant, inputs = ci_join.stage(kernel, output, work, baseline)
    for name in NAMES:
        shutil.copyfile(HERE / name, variant / name)
    with (variant / 'Makefile').open('a') as stream:
        stream.write('obj-y += ' + UNIT + '.o\n')
    return variant, inputs, digests


def native_command(variant, executable):
    return [os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
            '-DGPUEB_DRAM_HOST_TEST', '-I' + str(variant.resolve()), variant / 'test-dram.c', '-o', executable]


def build(args):
    ci_join.require(os.environ.get('CI') == 'true' and os.environ.get('GITHUB_ACTIONS') == 'true',
                    'DRAM compilation/native fault execution is CI-only')
    kernel, output, work, report = [path.resolve() for path in
                                    (args.kernel, args.output, args.work, args.report)]
    ci_join.disjoint(work, report, kernel, output)
    report.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'started', 'linux': PINS['linux'], 'pmaports': os.environ.get('GITHUB_SHA'),
                'scope': 'built-in candidate objects/private CMA mock faults; no publication, kernel link, or hardware test'}
    try:
        variant, inputs, digests = stage(kernel, output, work, args.baseline)
        manifest.update(dram_source_sha256=digests, input_sha256=inputs)
        manifest['compiler'] = subprocess.check_output(['clang', '--version'], text=True).strip()
        ci_join.require(re.search(r'clang version 21\.', manifest['compiler']), 'parent clang21 required')
        command = ci_join.kernel_command(kernel, work / 'output', variant) + [UNIT + '.o']
        manifest['kernel_command'] = list(map(str, command))
        ci_join.run(command)
        objects = [variant / (name + '.o') for name in (*ci_join.TRANSLATION_UNITS, UNIT)]
        manifest['objects'] = {path.name: {**ci_join.object_identity(path), 'sha256': ci_join.sha(path)}
                               for path in objects}
        formats = {item['format'] for item in manifest['objects'].values()}
        ci_join.require(len(formats) == 1, 'mixed object formats')
        linked = variant / 'owner-dram.o'
        ci_join.run(['llvm-link', '-o', linked, *objects] if formats == {'LLVM bitcode'} else
                    ['ld.lld', '-r', '-o', linked, *objects])
        defined = subprocess.check_output(['llvm-nm', '--defined-only', str(linked)], text=True)
        names = {line.split()[-1] for line in defined.splitlines() if line.split()}
        ci_join.require(set((*ci_join.JOIN_SYMBOLS, *API)) <= names, 'actual owner/DRAM API missing')
        imports = subprocess.check_output(['llvm-nm', '-u', str(linked)], text=True)
        raw_imports = {line.split()[-1] for line in imports.splitlines() if line.split()}
        manifest['raw_undefined_symbols'] = sorted(raw_imports)
        unresolved = sorted(raw_imports - names)
        manifest['unverified_kernel_imports'] = unresolved
        for path in [*objects, linked]:
            shutil.copyfile(path, report / path.name)
        ci_join.require(not any(name.startswith(('mt6878_gpueb_', 'gpueb_sram_', 'tetris_gpueb_flat_'))
                                for name in unresolved), 'unresolved internal owner API: ' + ', '.join(unresolved))
        manifest['kernel_link_boundary'] = 'cma_alloc/cma_release are built-in APIs, not module exports; partial link only'
        manifest['internal_link'] = {**ci_join.object_identity(linked), 'sha256': ci_join.sha(linked)}
        native = work / 'dram-mock-faults'
        manifest['native_command'] = list(map(str, native_command(variant, native)))
        ci_join.run(manifest['native_command'])
        result = ci_join.run([native], capture_output=True, text=True,
                             env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1', 'UBSAN_OPTIONS': 'halt_on_error=1'})
        (report / 'mock-faults.txt').write_text(result.stdout + result.stderr)
        manifest['mock_faults'] = 'passed; synthetic CMA history only, no firmware or MMIO'
        for path, digest in inputs.items():
            original = output / path if path == '.config' or path.startswith('include/') else kernel / path
            ci_join.require(ci_join.sha(original) == digest, 'shared source/config changed: ' + path)
        validate_kernel(kernel, output)
        ci_join.require(not list(variant.glob('*.ko')), 'unexpected runtime module')
        manifest['status'] = 'passed'
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        if isinstance(error, subprocess.CalledProcessError) and (error.stdout or error.stderr):
            (report / 'failure-output.txt').write_text((error.stdout or '') + (error.stderr or ''))
        raise
    finally:
        (report / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='source checks only; never compile or execute C')
    parser.add_argument('--kernel', type=Path, default=Path('/tmp/tetris-kernel-smoke/linux-' + PINS['linux']))
    parser.add_argument('--output', type=Path, default=Path('/tmp/tetris-kernel-smoke/objects'))
    parser.add_argument('--baseline', type=Path, default=ci_join.ROOT / 'out/kernel-object-smoke/BUILD-MANIFEST.json')
    parser.add_argument('--work', type=Path, default=Path('/tmp/tetris-gpueb-dram'))
    parser.add_argument('--report', type=Path, default=ci_join.ROOT / 'out/kernel-object-smoke/gpueb-dram')
    args = parser.parse_args()
    if args.check:
        print(json.dumps({'source_checks': 'passed', 'source_sha256': source_check(),
                          'scope': 'private allocation/loan candidate only; no compilation or activation'}, indent=2))
    else:
        build(args)


if __name__ == '__main__':
    main()
