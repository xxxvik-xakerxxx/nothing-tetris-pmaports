#!/usr/bin/env python3
"""Execute the generated AP-only module integration in GitHub CI only."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from package_metadata import build, candidate, HERE, PREFIX


BOUNDARY = r'''#ifndef PACKAGED_NATIVE_BOUNDARY_H
#define PACKAGED_NATIVE_BOUNDARY_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <asm-generic/errno.h>
#define __iomem
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define PAGE_SIZE TEST_PAGE_SIZE
#define pr_info(...) ((void)0)
#define WARN_ON(condition) ({ bool failed = !!(condition); assert(!failed); failed; })
#define THIS_MODULE ((void *)1)
void __module_get(void *);
typedef unsigned long long phys_addr_t;
typedef unsigned long long resource_size_t;
typedef uint32_t u32;
#define CurrentEL_EL1 (1UL << 2)
#define read_sysreg(reg) test_read_sysreg_##reg()
unsigned long test_read_sysreg_CurrentEL(void);
void *ioremap_wc(phys_addr_t, size_t);
unsigned int readl(const void *);
void iounmap(void *);
struct resource { resource_size_t start, end; };
#define resource_size(r) ((r)->end - (r)->start + 1)
struct resource *request_mem_region(resource_size_t, resource_size_t, const char *);
void release_mem_region(resource_size_t, resource_size_t);
struct mutex { bool locked; };
static inline void mutex_init(struct mutex *m) { m->locked = false; }
static inline void mutex_lock(struct mutex *m) { assert(!m->locked); m->locked = true; }
static inline void mutex_unlock(struct mutex *m) { assert(m->locked); m->locked = false; }
void *kzalloc(size_t, int);
void kfree(void *);
unsigned int get_unaligned_le32(const void *);
uint64_t get_unaligned_le64(const void *);
#endif
'''


def fixture_sources(vendor):
    producer = candidate()
    _, sources = build(vendor)
    fixture, boot = producer.native_fixture_sources(vendor)
    fixture = producer.replace(fixture, (HERE / 'owned_tags.h').read_text(),
                               sources[PREFIX + 'owned_tags.h'])
    for signature in ('void kfree(', 'unsigned int get_unaligned_le32(',
                      'uint64_t get_unaligned_le64('):
        fixture = producer.replace(fixture, 'static ' + signature, signature)
    args = sources[PREFIX + 'ccci_util_boot_args.c']
    start = args.index('void mtk_ccci_owned_args_cleanup(void)')
    end = args.index('\n#endif', start)
    fixture = producer.replace(fixture, 'void kernel_import_probe(',
        'static unsigned char *s_buf[8], *s_curr_ptr;\n'
        'static unsigned int s_curr_buf_idx, s_curr_buf_free;\n' +
        args[start:end] + '\n#include "test_packaged_smem.c"\n\n'
        'void kernel_import_probe(')
    fixture = producer.replace(fixture, '\tfree(expected);',
                               '\tpackaged_probe(&banks, ret);\n\tfree(expected);')
    return fixture, boot, sources


def native_ci(vendor, uboot, stock):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('native C compilation/execution is GitHub CI-only')
    producer = candidate()
    smem = producer.load('packaged_smem_types', HERE.parent / 'runtime-smem/check_smem.py')
    fixture, boot, sources = fixture_sources(vendor)
    with tempfile.TemporaryDirectory(prefix='packaged-smem-native-') as temp:
        root = Path(temp)
        for name, source in sources.items():
            path = root / name.removeprefix(PREFIX)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        for relative in ('linux/errno.h', 'linux/io.h', 'linux/kernel.h', 'linux/slab.h',
                         'linux/string.h', 'linux/unaligned.h', 'linux/mutex.h',
                         'linux/types.h', 'linux/of.h', 'linux/ioport.h', 'linux/module.h',
                         'asm/page.h', 'asm/ptrace.h', 'asm/sysreg.h'):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            headers = {'linux/errno.h': '#include <asm-generic/errno.h>\n',
                       'linux/string.h': '#include <string.h>\n'}
            path.write_text(headers.get(relative, '/* Native boundary only. */\n'))
        (root / 'boundary.h').write_text(BOUNDARY)
        (root / 'ap_md_mem.h').write_text(smem.native_types(vendor))
        (root / 'ccci_util_lib_main.h').write_text(
            '#include "metadata_resources.h"\n'
            'int mtk_ccci_find_args_val(const char *, unsigned char *, unsigned int);\n'
            'int mtk_ccci_owned_banks_copy(struct tetris_metadata_banks *);\n'
            'int mtk_ccci_owned_smem_init(void);\n'
            'void mtk_ccci_owned_smem_cleanup(void);\n')
        (root / 'import.c').write_text(fixture)
        (root / 'producer_test.c').write_text(boot)
        (root / 'test_packaged_smem.c').write_bytes((HERE / 'test_packaged_smem.c').read_bytes())
        (root / 'test_smem_reservation.c').write_bytes((HERE / 'test_smem_reservation.c').read_bytes())
        (root / 'test_initial_read.c').write_bytes((HERE / 'test_initial_read.c').read_bytes())
        names = ('tetris_modem_layout.c', 'tetris_modem_layout.h', 'tetris_modem_bundle.h',
                 'tetris_modem_emi.c', 'tetris_modem_emi.h', 'tetris_modem_remap.h',
                 'tetris_modem_emi_rows.c', 'tetris_modem_emi_rows.h',
                 'tetris_modem_ccci_tags.c', 'tetris_modem_ccci_tags.h',
                 'tetris_modem_loaded_boot.h', 'tetris_modem_bootstrap.h',
                 'tetris_modem_boot_secure.h')
        for name in names:
            (root / name).write_bytes(subprocess.check_output(['git', '-C', str(uboot),
                'show', f'{producer.UBOOT_PIN}:board/mediatek/mt6878/{name}']))
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1')
        profiles = ((4096, 0, 0), (65536, 0, 0), (4096, 1, 0), (65536, 1, 0),
                    (4096, 1, 1), (65536, 1, 1),
                    (4096, 0, None), (65536, 0, None),
                    (4096, 1, None), (65536, 1, None))
        for page, resource_only, initial_read in profiles:
            initial_flags = ([] if initial_read is None else
                [f'-DCONFIG_TETRIS_CCCI_SMEM_INITIAL_READ={initial_read}'])
            objects = []
            for name in ('tetris_modem_layout.c', 'tetris_modem_emi.c',
                         'tetris_modem_emi_rows.c', 'tetris_modem_ccci_tags.c',
                         'producer_test.c', 'import.c', 'tetris_runtime_smem/smem.c',
                         'tetris_runtime_smem/arguments.c', 'smem_boot_evidence/boot_evidence.c',
                         'smem_extent_preview.c', 'smem_reservation.c'):
                obj = root / (name.replace('/', '-') + '.o')
                flags = ['-include', str(root / 'boundary.h')] if name in (
                    'import.c', 'tetris_runtime_smem/smem.c', 'tetris_runtime_smem/arguments.c',
                    'smem_boot_evidence/boot_evidence.c', 'smem_extent_preview.c',
                    'smem_reservation.c') else []
                subprocess.run([os.environ.get('CC', 'clang'), '-std=gnu11', '-Wall', '-Wextra',
                    '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
                    '-fno-omit-frame-pointer', '-g', f'-DTEST_PAGE_SIZE={page}',
                    f'-DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY={resource_only}',
                    *initial_flags,
                    '-DTETRIS_MODEM_LAYOUT_HOST_TEST', '-I', str(root), *flags,
                    '-c', str(root / name), '-o', str(obj)], check=True)
                objects.append(str(obj))
            binary = root / f'packaged-smem-{page}-{resource_only}-{initial_read}'
            subprocess.run([os.environ.get('CC', 'clang'), '-fsanitize=address,undefined',
                            *objects, '-o', str(binary)], check=True)
            for case in range(59):
                subprocess.run([str(binary), str(stock), str(case)], env=env, check=True)
    print('actual packaged import -> SMEM plan: 59 cases x 4KiB/64KiB x '
          'metadata/resource/initial-read profiles PASS; initial-read I/O is mocked')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--uboot', type=Path, required=True)
    parser.add_argument('--stock-container', type=Path, required=True)
    args = parser.parse_args()
    native_ci(args.vendor.resolve(), args.uboot.resolve(), args.stock_container.resolve())


if __name__ == '__main__':
    main()
