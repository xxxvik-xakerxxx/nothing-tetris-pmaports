#!/usr/bin/env python3
"""Generate/check pinned SMEM source subsets. Native C execution is CI-only."""
import argparse
import difflib
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
VENDOR_PIN = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
UBOOT_PIN = '60cd9ade5b999732304f3b755c7dbe3d34307c13'
METADATA_PIN = '190ea155e1a8343dbdb4f0992f06b92848c9cdac'
VENDOR_PREFIX = 'drivers/misc/mediatek/'
PRODUCTION = ('arguments.c', 'private.h', 'smem.c', 'smem.h', 'source_model.h')
DESTINATION = VENDOR_PREFIX + 'ccci_util/tetris_runtime_smem/'


def source(tree, pin, path):
    return subprocess.check_output(['git', '-C', str(tree), 'show', f'{pin}:{path}'], text=True)


def function(text, name):
    match = re.search(r'^(?:static )?(?:unsigned int|int) ' + name + r'\([^;]+?\n\{\n.*?^\}',
                      text, re.M | re.S)
    if not match:
        raise ValueError('missing pinned function: ' + name)
    return match[0]


def generated_model(vendor, uboot, pmaports):
    header = source(uboot, UBOOT_PIN, 'board/mediatek/mt6878/tetris_modem_layout.h')
    layout = source(uboot, UBOOT_PIN, 'board/mediatek/mt6878/tetris_modem_layout.c')
    semantic = source(pmaports, METADATA_PIN, 'patches/modem/drafts/runtime-metadata/semantic.h')
    structs = []
    for name in ('smem_entry', 'smem_inputs', 'smem_plan'):
        match = re.search(r'^struct tetris_modem_' + name + r' \{.*?^\};', header, re.M | re.S)
        if not match:
            raise ValueError('missing pinned structure: ' + name)
        structs.append(match[0])
    functions = [function(layout, name) for name in ('word', 'smem_place', 'tetris_modem_plan_smem_b41')]
    functions[-1] = functions[-1].replace('int tetris_modem_plan_smem_b41(',
                                         'static int tetris_modem_plan_smem_b41(', 1)
    functions.append(function(semantic, 'tetris_metadata_windows'))
    ap = source(vendor, VENDOR_PIN, VENDOR_PREFIX + 'eccci/fsm/ap_md_mem.c')
    templates = []
    for original, new, expected in (('md1_noncacheable_tbl', 'tetris_nc_template', 26),
                                    ('md1_cacheable_tbl', 'tetris_cache_template', 11)):
        match = re.search(r'static struct ccci_smem_region ' + original + r'\[\] = \{.*?^\};',
                          ap, re.M | re.S)
        if not match:
            raise ValueError('missing pinned template: ' + original)
        body = re.sub(r'/\*.*?\*/', '', match[0], flags=re.S)
        rows = re.findall(r'\{([^{}]*)\}', body)
        if len(rows) != expected:
            raise ValueError('template row count drift: ' + original)
        full = []
        for row in rows:
            fields = [item.strip() for item in row.split(',') if item.strip()]
            if len(fields) not in (1, 4):
                raise ValueError('template initializer drift')
            full.append('\t{ ' + ', '.join(fields + ['0'] * (7 - len(fields))) + ' },')
        templates.append('static const struct ccci_smem_region ' + new + '[] = {\n' +
                         '\n'.join(full) + '\n};')
    return ('/* SPDX-License-Identifier: GPL-2.0-only */\n'
            '/* Generated pinned source subsets; NO physical reads or admission. */\n'
            f'/* U-Boot {UBOOT_PIN}; vendor {VENDOR_PIN}; metadata {METADATA_PIN}. */\n'
            '#ifndef TETRIS_RUNTIME_SMEM_SOURCE_MODEL_H\n#define TETRIS_RUNTIME_SMEM_SOURCE_MODEL_H\n\n' +
            '\n\n'.join(structs + functions + templates) + '\n#endif\n')


def native_types(vendor):
    common = source(vendor, VENDOR_PIN, VENDOR_PREFIX + 'include/mt-plat/mtk_ccci_common.h')
    ap = source(vendor, VENDOR_PIN, VENDOR_PREFIX + 'eccci/fsm/ap_md_mem.h')
    enum = re.search(r'^enum SMEM_USER_ID \{.*?^\};', common, re.M | re.S)
    flags = re.search(r'^enum \{.*?^\};', ap, re.M | re.S)
    types = [re.search(r'^struct ' + name + r' \{.*?^\};', ap, re.M | re.S)[0]
             for name in ('ccci_mem_region', 'ccci_smem_region', 'ccci_mem_layout')]
    return '#ifndef NATIVE_AP_MD_MEM_H\n#define NATIVE_AP_MD_MEM_H\n' + \
        '\n'.join([enum[0], flags[0]] + types) + '\n#endif\n'


def patch_text():
    chunks = []
    for name in sorted(PRODUCTION):
        target = DESTINATION + name
        chunks.extend((f'diff --git a/{target} b/{target}\n', 'new file mode 100644\n'))
        chunks.extend(difflib.unified_diff([], (HERE / name).read_text().splitlines(True),
                                         fromfile='/dev/null', tofile='b/' + target))
    return ''.join(chunks)


def check_stack(vendor, uboot):
    """Source export/application only. No configuration, make or C compiler."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('smem_stack', HERE.parent / 'runtime-object-ci/check_objects.py')
    staging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(staging)
    manifest, _, package = staging.plan()
    with tempfile.TemporaryDirectory(prefix='runtime-smem-apply-') as temporary:
        work = Path(temporary)
        destination = work / 'vendor'
        staging.stage_vendor(vendor, destination, package, manifest)
        staging.stage_metadata(vendor, destination, uboot, manifest, work / 'diagnostics')
        metadata = destination / VENDOR_PREFIX / 'ccci_util/metadata_resources.h'
        expected = source(HERE.parents[3], METADATA_PIN,
                          'patches/modem/drafts/runtime-metadata/metadata_resources.h')
        if metadata.read_text() != expected:
            raise ValueError('published resource ABI differs from exact source pin')
        patch = patch_text()
        subprocess.run(['git', 'apply', '--check', '-'], input=patch,
                       text=True, cwd=destination, check=True)
        subprocess.run(['git', 'apply', '-'], input=patch,
                       text=True, cwd=destination, check=True)
        for name in PRODUCTION:
            if (destination / DESTINATION / name).read_bytes() != (HERE / name).read_bytes():
                raise ValueError('staged SMEM production source drift: ' + name)
    print('source-only complete stack + metadata + SMEM source overlay PASS')


def stock_footer(container):
    """Public file only. Not kernel RAM, authentication or a hardware selector."""
    with container.open('rb') as stream:
        header = stream.read(512)
        if len(header) != 512 or struct.unpack_from('<I', header)[0] != 0x58881688 or \
                header[8:40].split(b'\0', 1)[0] != b'md1rom':
            raise ValueError('expected existing public plaintext md1rom container')
        length = struct.unpack_from('<I', header, 4)[0]
        if length < 512 or length > 64 * 1024 * 1024 or length & 15:
            raise ValueError('bounded md1rom length')
        stream.seek(512 + length - 512)
        footer = stream.read(512)
        if len(footer) != 512 or footer[:12] != b'CHECK_HEADER':
            raise ValueError('missing exact CHK footer')
        return footer


def native_ci(vendor, uboot, pmaports, container):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('native compilation/execution only allowed in GitHub CI')
    verify(vendor, uboot, pmaports)
    with tempfile.TemporaryDirectory(prefix='tetris-smem-ci-') as temporary:
        work = Path(temporary)
        for relative in ('linux/errno.h', 'linux/io.h', 'linux/kernel.h', 'linux/slab.h', 'linux/string.h',
                         'linux/unaligned.h', 'linux/types.h', 'linux/mutex.h', 'asm/page.h',
                         'ccci_util_lib_main.h'):
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('/* Native boundary supplied by test_smem.c. */\n')
        (work / 'ap_md_mem.h').write_text(native_types(vendor))
        metadata = source(pmaports, METADATA_PIN,
                          'patches/modem/drafts/runtime-metadata/metadata_resources.h')
        (work / 'metadata_resources.h').write_text(metadata)
        footer = work / 'stock-chk.bin'
        footer.write_bytes(stock_footer(container))
        for page in (4096, 65536):
            executable = work / f'test-smem-{page}'
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
                            f'-DTEST_PAGE_SIZE={page}', '-I', str(work), '-I', str(HERE),
                            str(HERE / 'test_smem.c'), '-o', str(executable)], check=True)
            for case in range(70):
                subprocess.run([str(executable), str(case), str(footer)], check=True)
    print('SMEM native strict/sanitized 70 cases x 4KiB/64KiB pages PASS')


def verify(vendor, uboot, pmaports):
    expected = generated_model(vendor, uboot, pmaports)
    if (HERE / 'source_model.h').read_text() != expected:
        raise SystemExit('source-model drift; do not silently regenerate in CI')
    if (HERE / 'runtime-smem.patch.vendor').read_text() != patch_text():
        raise SystemExit('reviewed source overlay drift')
    print('pinned source model PASS ' + hashlib.sha256(expected.encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--uboot', type=Path, required=True)
    parser.add_argument('--pmaports', type=Path, default=HERE.parents[3])
    parser.add_argument('--emit-model', action='store_true')
    parser.add_argument('--emit-patch', action='store_true')
    parser.add_argument('--check-stack', action='store_true')
    parser.add_argument('--emit-review', action='store_true')
    parser.add_argument('--native-ci', action='store_true')
    parser.add_argument('--stock-container', type=Path)
    args = parser.parse_args()
    if args.emit_model:
        (HERE / 'source_model.h').write_text(generated_model(args.vendor, args.uboot, args.pmaports))
    if args.emit_patch:
        (HERE / 'runtime-smem.patch.vendor').write_text(patch_text())
    verify(args.vendor, args.uboot, args.pmaports)
    if args.check_stack:
        check_stack(args.vendor, args.uboot)
    if args.native_ci:
        if not args.stock_container:
            parser.error('--native-ci requires existing public --stock-container')
        native_ci(args.vendor, args.uboot, args.pmaports, args.stock_container)
    if args.emit_review:
        names = ('README.md', 'arguments.c', 'check_smem.py', 'private.h',
                 'runtime-smem.patch.vendor', 'smem.c', 'smem.h', 'source_model.h',
                 'test_smem.c', 'test_static.py')
        (HERE / 'REVIEW.sha256').write_text(''.join(
            f'{hashlib.sha256((HERE / name).read_bytes()).hexdigest()}  {name}\n' for name in names))


if __name__ == '__main__':
    main()
