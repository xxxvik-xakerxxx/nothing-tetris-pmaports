#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Isolated CI owner-join objects/internal link and mocked faults; no installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from generate_join_patch import HERE, ROOT, render

LINUX = 'd84b264a54a37611f2f46bc19363cb9b41606205'
RESEARCH = 'drivers/soc/mediatek/tetris-owner-smoke/'
EXTRA_PINS = {
    'patches/gpu/sram-owner/mt6878-gpueb-sram-core.c':
        '9c2538da73f91c505f1cc541ed09ce602c0deb563b96f18d21819dec96a7246b',
    'patches/gpu/sram-owner/mt6878-gpueb-sram-core.h':
        '8631d394e10d2669eab676efe727bdc4834e69605f33e863a7a2147784f4e585',
    'patches/gpu/sram-owner/sram-host.h':
        '09d8d392a66035ade03b516d815aacf0dffdb8b3397f63fd8b0eb42a21ff871a',
    'patches/gpu/reset-owner-draft/reset-host.h':
        'e06cd66edf8251c3f3966e4c507c3c984e77de1a7e9062288b9eebc91935df99',
}
TRANSLATION_UNITS = ('gpueb-flat-analysis', 'mt6878-gpueb-sram',
                     'mt6878-gpueb-sram-core', 'mt6878-gpueb-reset')
JOIN_SYMBOLS = ('tetris_gpueb_flat_use_primary', 'mt6878_gpueb_sram_install_retained',
                'mt6878_gpueb_reset_primary_transaction')

NATIVE = r'''// SPDX-License-Identifier: GPL-2.0-only
/* CI mock history only. This is not firmware authentication or hardware state. */
#include "reset-host.h"
#include <stdio.h>
typedef unsigned char u8;
struct miscdevice { int unused; };
struct platform_driver { struct device_driver driver; };
static struct platform_driver flat_driver;
static struct platform_device input_device;
static pthread_mutex_t input_lock = PTHREAD_MUTEX_INITIALIZER;
static void *input_data;
static void device_lock(struct device *dev)
{ assert(dev == &input_device.dev); assert(!pthread_mutex_lock(&input_lock)); }
static void device_unlock(struct device *dev)
{ assert(dev == &input_device.dev); assert(!pthread_mutex_unlock(&input_lock)); }
static void *platform_get_drvdata(struct platform_device *dev)
{ assert(dev == &input_device); return input_data; }
#define TETRIS_FLAT_BYTES 156064U
#ifndef EPROBE_DEFER
#define EPROBE_DEFER 517
#endif
#include "flat-structs.inc"
#include "flat-loan.inc"
static void mock_clear(void *mapping, int value, size_t bytes);
#define memset_io mock_clear
#define wmb() fixture_barrier()
#include "mt6878-gpueb-sram-core.c"
#include "mt6878-gpueb-sram.c"
#include "mt6878-gpueb-reset.c"

static struct mt6878_gpueb_reset scope;
static struct device parent, client;
static struct module owner_module;
static struct device_driver owner_driver = { &owner_module, 1 };
static struct flat_analysis analysis;
static unsigned char *memory, *primary;
static u32 registers[0x2000 / 4];
static struct resource reservation;
static unsigned int reset_writes, image_writes, clears, reads, claimed;
static int bad_latch, bad_readback, reenable_in_drain;

static void *kzalloc(size_t bytes, int flags)
{ assert(flags == GFP_KERNEL); return calloc(1, bytes); }
static void kfree(void *ptr)
{
    if (ptr == scope.sram) assert(!pthread_mutex_destroy(&scope.sram->lock.value));
    free(ptr);
}
static struct resource *request_mem_region(uint64_t start, uint64_t size, const char *name)
{
    assert(!claimed && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE && name);
    claimed = 1;
    reservation = (struct resource){ start, start + size - 1, IORESOURCE_MEM };
    return &reservation;
}
static void release_mem_region(uint64_t start, uint64_t size)
{ assert(claimed && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE); claimed = 0; }
static void *ioremap(uint64_t start, uint64_t size)
{
    assert(claimed && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE);
    memory = malloc(size); assert(memory); memset(memory, 0xa5, size); return memory;
}
static void iounmap(void *ptr) { assert(ptr == memory); free(ptr); memory = NULL; }
static void assert_scope_lock(void)
{
    assert(pthread_mutex_trylock(&scope.lock.value) == EBUSY);
    assert(pthread_mutex_trylock(&input_lock) == EBUSY);
}
static uint32_t readl(const void *mapping)
{
    u32 value;
    assert_scope_lock(); reads++;
    if (mapping == &registers[0x600 / 4]) {
        assert(reset_writes == 1);
        return bad_latch ? 1 : registers[0x600 / 4];
    }
    assert(pthread_mutex_trylock(&scope.sram->lock.value) == EBUSY);
    assert((uintptr_t)mapping >= (uintptr_t)memory &&
           (uintptr_t)mapping + 4 <= (uintptr_t)memory + GPUEB_SRAM_SIZE);
    memcpy(&value, mapping, 4);
    if (bad_readback && mapping == memory + GPUEB_SRAM_SIZE - 4) value ^= 1;
    return value;
}
static void writel(uint32_t word, void *mapping)
{
    assert_scope_lock();
    assert(scope.sram->core.phase == GPUEB_SRAM_QUARANTINED);
    if (mapping == &registers[0x600 / 4]) {
        assert(scope.reset_written && word == 0 && !clears && !image_writes);
        reset_writes++;
    } else {
        assert(pthread_mutex_trylock(&scope.sram->lock.value) == EBUSY);
        assert(reset_writes == 1 && clears == 1);
        assert((uintptr_t)mapping >= (uintptr_t)memory &&
               (uintptr_t)mapping + 4 <= (uintptr_t)memory + TETRIS_FLAT_BYTES);
        image_writes++;
    }
    memcpy(mapping, &word, 4);
}
static void mock_clear(void *mapping, int value, size_t bytes)
{
    assert_scope_lock();
    assert(pthread_mutex_trylock(&scope.sram->lock.value) == EBUSY);
    assert(mapping == memory && value == 0 && bytes == GPUEB_SRAM_SIZE && reset_writes == 1);
    clears++; memset(mapping, value, bytes);
}
static void fixture_barrier(void)
{ assert_scope_lock(); assert(pthread_mutex_trylock(&scope.sram->lock.value) == EBUSY); }
static void fixture_synchronize(void)
{
    assert(!pthread_mutex_trylock(&scope.lock.value));
    assert(!pthread_mutex_unlock(&scope.lock.value));
    if (reenable_in_drain) fixture_irq_data.disabled = 0;
}
static void receive(void *data, unsigned int channel, const u32 *words, unsigned int count)
{ (void)data; (void)channel; (void)words; (void)count; abort(); }

static void setup(void)
{
    unsigned int i;
    struct resource res = { GPUEB_SRAM_BASE, GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1, IORESOURCE_MEM };
    memset(&scope, 0, sizeof(scope)); memset(&analysis, 0, sizeof(analysis));
    memset(registers, 0xa5, sizeof(registers));
    parent = (struct device){ .driver = &owner_driver };
    client = (struct device){ .driver = &owner_driver };
    owner_module.refs = 0; fixture_pm_refs = 1; /* Mock prepare's retained PM reference. */
    fixture_pm_get_result = 1; fixture_module_fail = NULL; fixture_irq_data.disabled = 1;
    reset_writes = image_writes = clears = reads = 0;
    bad_latch = bad_readback = reenable_in_drain = 0;
    fixture_masks = fixture_syncs = 0;
    mutex_init(&scope.lock); spin_lock_init(&scope.irq_lock);
    scope.parent = get_device(&parent); scope.parent_driver = parent.driver;
    scope.irq = 273; scope.registers = registers;
    scope.sram = mt6878_gpueb_sram_create(&parent, &res); assert(!IS_ERR(scope.sram));
    scope.gpr = mt6878_gpueb_sram_get_window(scope.sram, GPUEB_WINDOW_GPR);
    scope.mbox = mt6878_gpueb_sram_get_window(scope.sram, GPUEB_WINDOW_MBOX);
    assert(!IS_ERR(scope.gpr) && !IS_ERR(scope.mbox));
    for (i = 0; i < 11; i++)
        assert(!mt6878_gpueb_reset_bind_channel(&scope, &client, i, receive, NULL));
    assert(!IS_ERR(mt6878_gpueb_reset_dispatch_acquire(&scope, &parent)));
    input_device.dev.driver = &flat_driver.driver;
    primary = malloc(TETRIS_FLAT_BYTES); assert(primary);
    for (i = 0; i < TETRIS_FLAT_BYTES; i++) primary[i] = (unsigned char)(i * 37U);
    /* Private fixture construction of successful admission history only.
     * ARM64 builds separately compile the entire actual authentication path.
     */
    analysis.snapshot = primary; analysis.size = TETRIS_FLAT_BYTES;
    analysis.metadata.profile_id = 1; analysis.reservation = &reservation;
    input_data = &analysis;
}
static void dispose(void)
{
    unsigned int i;
    struct mt6878_gpueb_sram *sram = scope.sram;
    if (scope.reset_written) {
        assert(scope.dispatch_owner && fixture_pm_refs == 2);
        assert(mt6878_gpueb_reset_destroy(&scope) == (scope.first_error ?: -EBUSY));
        assert(sram->core.phase == GPUEB_SRAM_QUARANTINED && claimed);
    }
    /* Mock teardown only, AFTER production APIs prove retention. No runtime escape. */
    if (scope.dispatch_owner) {
        pm_runtime_put_noidle(scope.dispatch_owner->parent);
        put_device(scope.dispatch_owner->parent); module_put(scope.dispatch_owner->module);
        free(scope.dispatch_owner); scope.dispatch_owner = NULL;
    }
    for (i = 0; i < 11; i++) {
        put_device(scope.channels[i].device); module_put(scope.channels[i].module);
    }
    mt6878_gpueb_sram_put_window(scope.gpr); mt6878_gpueb_sram_put_window(scope.mbox);
    if (sram->core.phase == GPUEB_SRAM_QUARANTINED) {
        assert(mt6878_gpueb_sram_destroy(sram) == -EBUSY);
        iounmap(sram->mapping); release_mem_region(GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE);
        put_device(sram->parent);
        assert(!pthread_mutex_destroy(&sram->lock.value)); free(sram);
    } else {
        assert(!mt6878_gpueb_sram_destroy(sram));
    }
    pm_runtime_put_noidle(scope.parent); put_device(scope.parent);
    assert(!parent.refs && !client.refs && !owner_module.refs && !claimed && !fixture_pm_refs);
    free(primary);
    assert(!pthread_mutex_destroy(&scope.lock.value)); assert(!pthread_mutex_destroy(&scope.irq_lock));
}
static int install(void)
{ return mt6878_gpueb_sram_install_retained(scope.sram, &scope, &input_device); }
int main(void)
{
    unsigned int i, mode;
    for (mode = 0; mode < 6; mode++) {
        setup();
        if (mode == 0) input_device.dev.driver = &owner_driver;
        if (mode == 1) analysis.snapshot = NULL;
        if (mode == 2) analysis.metadata.profile_id = 2;
        if (mode == 3) analysis.size += 4;
        if (mode == 4) analysis.reservation = NULL;
        if (mode == 5) input_data = NULL;
        assert(install() == (mode == 0 ? -ENODEV : mode == 1 || mode > 3 ? -EPROBE_DEFER : -ENOEXEC));
        assert(!reset_writes && !clears && !image_writes && !reads && !fixture_syncs);
        dispose();
    }
    setup();
    { struct mt6878_gpueb_sram other = { 0 };
      assert(mt6878_gpueb_sram_install_retained(&other, &scope, &input_device) == -ENODEV); }
    assert(!reset_writes && !fixture_syncs); dispose();
    setup(); fixture_pm_get_result = 0;
    assert(install() == -EAGAIN && !reset_writes && !clears); dispose();
    setup(); fixture_pm_get_result = -ENOSYS;
    assert(install() == -ENOSYS && !reset_writes && !clears); dispose();
    setup(); scope.first_error = -ETIMEDOUT;
    assert(install() == -ETIMEDOUT && !reset_writes && !fixture_syncs); dispose();
    setup(); scope.dispatch_active = true;
    assert(install() == -EALREADY && !reset_writes && !fixture_syncs);
    scope.dispatch_active = false; dispose();
    setup(); reenable_in_drain = 1;
    assert(install() == -EBUSY && !reset_writes && !clears); dispose();
    setup(); client.driver = NULL;
    assert(install() == -ENODEV && !reset_writes && !clears); client.driver = &owner_driver; dispose();
    for (mode = 0; mode < 3; mode++) {
        setup(); bad_latch = mode == 0; bad_readback = mode == 1;
        assert(install() == (mode < 2 ? -EIO : 0));
        assert(reset_writes == 1 && scope.reset_written && scope.dispatch_quiesced);
        assert(!scope.dispatch_active && fixture_irq_data.disabled);
        assert(clears == (mode == 0 ? 0U : 1U));
        assert(image_writes == (mode == 0 ? 0U : TETRIS_FLAT_BYTES / 4));
        if (mode == 2) {
            assert(!memcmp(memory, primary, TETRIS_FLAT_BYTES));
            for (i = TETRIS_FLAT_BYTES; i < GPUEB_SRAM_SIZE; i++) assert(!memory[i]);
        }
        { unsigned int previous = reset_writes + image_writes;
          assert(install() == -EALREADY);
          assert(scope.first_error == (mode < 2 ? -EIO : 0));
          assert(previous == reset_writes + image_writes); }
        dispose();
    }
    puts("PASS: canonical loan/reset/SRAM join mocked faults; no real firmware or hardware execution");
    return 0;
}
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def checked_sources():
    patch, joined = render()
    require(patch == (HERE / 'owner-join.patch').read_text(), 'stale owner join delta')
    for path, digest in EXTRA_PINS.items():
        require(sha(ROOT / path) == digest, 'source drift: ' + path)
    files = {Path(path).name: source for path, source in joined.items()}
    for path in EXTRA_PINS:
        files[Path(path).name] = (ROOT / path).read_text()
    loan = (HERE / 'flat-input.inc').read_text()
    require(files['gpueb-flat-analysis.c'].count(loan) == 1, 'loan differs from compiled canonical source')
    for name in ('tetris_gpueb_flat_metadata', 'flat_analysis'):
        text = files['gpueb-flat-analysis.c']
        start = text.index('struct ' + name + ' {')
        end = text.index('\n};', start) + 3
        files.setdefault('flat-structs.inc', '')
        files['flat-structs.inc'] += text[start:end] + '\n'
    files['flat-loan.inc'] = loan
    files['test-join.c'] = NATIVE
    # Never put a mocked Linux header on the actual kernel compile search path.
    files['host-include/linux/unaligned.h'] = (
        '#include <stdint.h>\nstatic inline uint32_t get_unaligned_le32(const void *ptr)\n'
        '{ const unsigned char *p = ptr; return (uint32_t)p[0] | (uint32_t)p[1] << 8 | '
        '(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }\n')
    return files


def prepared_inputs(kernel, output, baseline):
    manifest = json.loads(baseline.read_text())
    require(manifest.get('status') == 'passed' and manifest.get('kernel_commit') == LINUX,
            'successful pinned research-owner build required')
    files = checked_sources()
    original = json.loads((HERE / 'SOURCE-PINS.json').read_text())['sources']
    originals = {'drivers/misc/gpueb-flat-analysis.c': original[
        'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c']}
    require(manifest.get('gpueb_flat_v1', {}).get('source_sha256') ==
            originals['drivers/misc/gpueb-flat-analysis.c'], 'baseline lacks actual canonical consumer')
    for path, digest in original.items():
        if '/sram-owner/' in path or '/reset-owner-draft/' in path:
            originals[RESEARCH + Path(path).name] = digest
            require(manifest.get('research_source_sha256', {}).get(path) == digest,
                    'baseline lacks exact research owner: ' + path)
    for path, digest in EXTRA_PINS.items():
        if Path(path).name.startswith('mt6878-'):
            originals[RESEARCH + Path(path).name] = digest
            require(manifest.get('research_source_sha256', {}).get(path) == digest,
                    'baseline lacks exact core: ' + path)
    for path, digest in originals.items():
        require(sha(kernel / path) == digest, 'prepared source drift: ' + path)
    for path in output.rglob('*'):
        if path.is_symlink():
            # Kbuild's source link is read-only in external-object mode. Any
            # other link could make a copied O= write into shared build data.
            require(path == output / 'source' and path.resolve() == kernel.resolve(),
                    'unsafe prepared-output symlink: ' + str(path))
    config = (output / '.config').read_text().splitlines()
    for option in ('CONFIG_MODULES=y', 'CONFIG_OF=y', 'CONFIG_OF_ADDRESS=y', 'CONFIG_OF_RESERVED_MEM=y'):
        require(option in config, 'prepared kernel dependency missing: ' + option)
    for path in ('.config', 'include/generated/autoconf.h', 'include/config/auto.conf'):
        require((output / path).is_file(), 'prepared kernel configuration missing: ' + path)
        originals[path] = sha(output / path)
    return files, originals


def disjoint(work, report, kernel, output):
    paths = [path.resolve() for path in (work, report, kernel, output)]
    for index, left in enumerate(paths[:2]):
        for right in paths[index + 1:]:
            require(left != right and not left.is_relative_to(right) and not right.is_relative_to(left),
                    'variant paths overlap input/output trees')


def stage(kernel, output, work, baseline):
    files, fingerprints = prepared_inputs(kernel, output, baseline)
    work.mkdir(parents=True, exist_ok=False)
    variant = work / 'source'
    variant.mkdir()
    for name, text in files.items():
        target = variant / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (variant / 'Makefile').write_text('obj-y += ' + ' '.join(name + '.o' for name in TRANSLATION_UNITS) + '\n')
    # Preserve the real configured/generated headers and compiler support files.
    # A private O= copy prevents changes to the parent's config/object collection.
    shutil.copytree(output, work / 'output', symlinks=True)
    return variant, fingerprints


def run(argv, **kwargs):
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def object_identity(path):
    magic = path.read_bytes()[:4]
    if magic in (b'BC\xc0\xde', b'\xde\xc0\x17\x0b'):
        ir = subprocess.check_output(['llvm-dis', '-o', '-', str(path)], text=True)
        triples = re.findall(r'^target triple = "([^"]+)"$', ir, re.M)
        require(len(triples) == 1 and triples[0].startswith('aarch64-'), 'wrong LLVM target')
        return {'format': 'LLVM bitcode', 'target': triples[0]}
    header = subprocess.check_output(['llvm-readelf', '-h', str(path)], text=True)
    require(magic == b'\x7fELF' and re.search(r'Machine:\s+AArch64', header), 'wrong ELF target')
    return {'format': 'ELF', 'target': 'AArch64'}


def kernel_command(kernel, output, variant):
    return ['make', '-C', kernel, 'O=' + str(output.resolve()),
            'M=' + str(variant.resolve()), 'ARCH=arm64', 'LLVM=1', '-j4', 'KCFLAGS=-Werror',
            *(name + '.o' for name in TRANSLATION_UNITS)]


def fault_command(variant, native):
    return [os.environ.get('HOSTCC', 'cc'), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
            '-DGPUEB_RESET_HOST_TEST', '-DGPUEB_SRAM_HOST_TEST', '-I' + str(variant.resolve()),
            '-I' + str((variant / 'host-include').resolve()), variant / 'test-join.c', '-o', native]


def build(kernel, output, work, report, baseline):
    require(os.environ.get('CI') == 'true' and os.environ.get('GITHUB_ACTIONS') == 'true',
            'compilation/fault execution is CI-only')
    disjoint(work, report, kernel, output)
    report.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'started', 'linux': LINUX, 'pmaports': os.environ.get('GITHUB_SHA'),
                'scope': 'isolated objects/internal partial link and mock faults; kernel exports/hardware untested'}
    try:
        variant, inputs = stage(kernel, output, work, baseline)
        manifest['input_sha256'] = inputs
        manifest['compiler'] = subprocess.check_output(['clang', '--version'], text=True).strip()
        require(re.search(r'clang version 21\.', manifest['compiler']), 'parent package-matching clang21 required')
        manifest['variant_source_sha256'] = {
            str(path.relative_to(variant)): sha(path) for path in variant.rglob('*') if path.is_file()}
        manifest['kernel_command'] = list(map(str, kernel_command(kernel, work / 'output', variant)))
        run(manifest['kernel_command'])
        objects = [variant / (name + '.o') for name in TRANSLATION_UNITS]
        manifest['objects'] = {path.name: {**object_identity(path), 'sha256': sha(path)} for path in objects}
        formats = {item['format'] for item in manifest['objects'].values()}
        require(len(formats) == 1, 'mixed object formats')
        joined = variant / 'owner-join.o'
        run(['llvm-link', '-o', joined, *objects] if formats == {'LLVM bitcode'} else
            ['ld.lld', '-r', '-o', joined, *objects])
        manifest['internal_link'] = {**object_identity(joined), 'sha256': sha(joined)}
        defined = subprocess.check_output(['llvm-nm', '--defined-only', str(joined)], text=True)
        undefined = subprocess.check_output(['llvm-nm', '-u', str(joined)], text=True)
        symbols = {line.split()[-1] for line in defined.splitlines() if line.split()}
        require(set(JOIN_SYMBOLS) <= symbols, 'new owner API definition absent from partial link')
        raw_imports = {line.split()[-1] for line in undefined.splitlines() if line.split()}
        manifest['raw_undefined_symbols'] = sorted(raw_imports)
        # Inline export assembly can name a symbol also defined in linked IR.
        # Keep only exact-name imports without a definition, never prefix aliases.
        imports = sorted(raw_imports - symbols)
        manifest['unverified_kernel_imports'] = imports
        for path in [*objects, joined]:
            shutil.copyfile(path, report / path.name)
        require(not any(name.startswith(('mt6878_gpueb_', 'gpueb_sram_', 'tetris_gpueb_flat_'))
                        for name in imports), 'unresolved internal GPU owner dependency: ' + ', '.join(imports))
        native = work / 'mock-faults'
        manifest['fault_command'] = list(map(str, fault_command(variant, native)))
        run(manifest['fault_command'])
        result = run([native], capture_output=True, text=True,
                     env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1', 'UBSAN_OPTIONS': 'halt_on_error=1'})
        (report / 'mock-faults.txt').write_text(result.stdout + result.stderr)
        manifest['mock_faults'] = 'passed; synthetic admission history and mocked MMIO only'
        shutil.copyfile(work / 'output/.config', report / 'config')
        for path, digest in inputs.items():
            source = output / path if path == '.config' or path.startswith('include/') else kernel / path
            require(sha(source) == digest, 'shared input modified: ' + path)
        require(not list(variant.glob('*.ko')), 'object variant unexpectedly produced a module')
        manifest['status'] = 'passed'
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        if isinstance(error, subprocess.CalledProcessError) and (error.stdout or error.stderr):
            (report / 'failure-output.txt').write_text((error.stdout or '') + (error.stderr or ''))
        raise
    finally:
        (report / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def test_static():
    """Scratch staging and command assertions only; never invoke a compiler/test binary."""
    import tempfile
    import unittest
    from unittest.mock import patch

    class Orchestration(unittest.TestCase):
        def setUp(self):
            self.tmp = tempfile.TemporaryDirectory(prefix='tetris-join-static-')
            self.addCleanup(self.tmp.cleanup)
            base = Path(self.tmp.name)
            self.kernel, self.output = base / 'kernel', base / 'output'
            self.work, self.report, self.baseline = base / 'work', base / 'report', base / 'baseline.json'
            self.pins = json.loads((HERE / 'SOURCE-PINS.json').read_text())['sources']
            self.originals = {'drivers/misc/gpueb-flat-analysis.c':
                              'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c'}
            research = {path: digest for path, digest in {**self.pins, **EXTRA_PINS}.items()
                        if '/sram-owner/' in path or '/reset-owner-draft/' in path}
            for path in research:
                if Path(path).name.startswith('mt6878-'):
                    self.originals[RESEARCH + Path(path).name] = path
            for target, source in self.originals.items():
                dest = self.kernel / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, dest)
            for path, content in {
                '.config': 'CONFIG_MODULES=y\nCONFIG_OF=y\nCONFIG_OF_ADDRESS=y\nCONFIG_OF_RESERVED_MEM=y\n',
                'include/generated/autoconf.h': '/* Static orchestration fixture, not kernel headers. */\n',
                'include/config/auto.conf': '# Static orchestration fixture.\n',
            }.items():
                dest = self.output / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
            # Synthetic baseline for control-flow tests only, never build evidence.
            self.manifest = {'status': 'passed', 'kernel_commit': LINUX,
                             'research_source_sha256': research,
                             'gpueb_flat_v1': {'source_sha256': self.pins[
                                 'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c']}}
            self.save()
            self.before = self.fingerprints()

        def save(self):
            self.baseline.write_text(json.dumps(self.manifest))

        def fingerprints(self):
            return {str(path): sha(path) for root in (self.kernel, self.output)
                    for path in root.rglob('*') if path.is_file()}

        def prepared(self):
            return prepared_inputs(self.kernel, self.output, self.baseline)

        def test_exact_join_sources_and_real_header_path(self):
            files, _ = self.prepared()
            _, joined = render()
            for path, content in joined.items():
                self.assertEqual(files[Path(path).name], content)
            self.assertIn('host-include/linux/unaligned.h', files)
            self.assertNotIn('linux/unaligned.h', files)
            for name in TRANSLATION_UNITS:
                self.assertIn(name + '.c', files)

        def test_isolated_stage_preserves_inputs(self):
            variant, _ = stage(self.kernel, self.output, self.work, self.baseline)
            self.assertEqual(self.fingerprints(), self.before)
            self.assertIn('mt6878_gpueb_sram_install_retained',
                          (variant / 'mt6878-gpueb-sram.c').read_text())
            (self.work / 'output/.config').write_text('private variant change\n')
            self.assertEqual(self.fingerprints(), self.before)
            self.assertFalse(list(variant.glob('*.o')))

        def test_bad_baseline_rejected(self):
            for key, value in (('status', 'started'), ('kernel_commit', 'wrong'),
                               ('research_source_sha256', {}), ('gpueb_flat_v1', {})):
                with self.subTest(key=key):
                    old = self.manifest[key]
                    self.manifest[key] = value
                    self.save()
                    with self.assertRaises(ValueError):
                        self.prepared()
                    self.manifest[key] = old
                    self.save()

        def test_prepared_source_drift_rejected(self):
            for name in self.originals:
                with self.subTest(source=name):
                    path = self.kernel / name
                    old = path.read_bytes()
                    path.write_bytes(old + b'\n')
                    with self.assertRaises(ValueError):
                        self.prepared()
                    path.write_bytes(old)

        def test_dependency_config_rejected(self):
            path = self.output / '.config'
            old = path.read_text()
            for option in old.splitlines():
                with self.subTest(option=option):
                    path.write_text(old.replace(option, '# ' + option))
                    with self.assertRaises(ValueError):
                        self.prepared()
            path.write_text(old)

        def test_generated_config_required(self):
            for name in ('include/generated/autoconf.h', 'include/config/auto.conf'):
                path = self.output / name
                old = path.read_bytes()
                path.unlink()
                with self.assertRaises(ValueError):
                    self.prepared()
                path.write_bytes(old)

        def test_path_aliases_rejected(self):
            disjoint(self.work, self.report, self.kernel, self.output)
            for work in (self.kernel, self.kernel / 'join', self.output, self.output.parent):
                with self.assertRaises(ValueError):
                    disjoint(work, self.report, self.kernel, self.output)
            with self.assertRaises(ValueError):
                disjoint(self.work, self.work / 'report', self.kernel, self.output)

        def test_existing_work_not_overwritten(self):
            self.work.mkdir()
            sentinel = self.work / 'preserve'
            sentinel.write_text('existing data\n')
            with self.assertRaises(FileExistsError):
                stage(self.kernel, self.output, self.work, self.baseline)
            self.assertEqual(sentinel.read_text(), 'existing data\n')

        def test_only_readonly_kbuild_source_symlink_allowed(self):
            (self.output / 'source').symlink_to(self.kernel, target_is_directory=True)
            self.prepared()
            (self.output / 'unsafe').symlink_to(self.output / '.config')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.prepared()

        def test_local_guard_precedes_writes_or_processes(self):
            for ci, actions in (('', ''), ('true', ''), ('', 'true')):
                with patch.dict(os.environ, CI=ci, GITHUB_ACTIONS=actions), \
                        patch('subprocess.run', side_effect=AssertionError('unexpected process')):
                    with self.assertRaisesRegex(ValueError, 'CI-only'):
                        build(self.kernel, self.output, self.work, self.report, self.baseline)
                self.assertFalse(self.work.exists())
                self.assertFalse(self.report.exists())

        def test_object_command_has_full_real_dependency(self):
            variant = self.work / 'source'
            command = list(map(str, kernel_command(self.kernel, self.work / 'output', variant)))
            self.assertEqual(command[-4:], [name + '.o' for name in TRANSLATION_UNITS])
            self.assertIn('M=' + str(variant.resolve()), command)
            self.assertIn('O=' + str((self.work / 'output').resolve()), command)
            self.assertFalse({'modules', 'modules_install', 'vmlinux'} & set(command))
            self.assertFalse(any('host-include' in arg for arg in command))

        def test_fault_command_and_retention_assertions(self):
            command = list(map(str, fault_command(self.work / 'source', self.work / 'mock-faults')))
            self.assertIn('-fsanitize=address,undefined', command)
            self.assertIn('-Werror', command)
            for assertion in ('bad_latch', 'bad_readback', 'reenable_in_drain',
                              'fixture_pm_get_result = 0', 'client.driver = NULL',
                              'GPUEB_SRAM_QUARANTINED && claimed', 'assert(install() == -EALREADY)',
                              'assert(scope.first_error == (mode < 2 ? -EIO : 0))'):
                self.assertIn(assertion, NATIVE)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Orchestration)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='source/pin checks only; no writes or compilation')
    parser.add_argument('--test-static', action='store_true', help='scratch orchestration tests; no compiler or C execution')
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'out/kernel-object-smoke/BUILD-MANIFEST.json')
    parser.add_argument('--work', type=Path, default=Path('/tmp/tetris-gpueb-boot-join'))
    parser.add_argument('--report', type=Path, default=ROOT / 'out/kernel-object-smoke/gpueb-boot-join')
    args = parser.parse_args()
    if args.test_static:
        test_static()
        return
    if args.check:
        files = checked_sources()
        print(json.dumps({'source_checks': 'passed', 'translation_units': TRANSLATION_UNITS,
                          'joined_api': JOIN_SYMBOLS, 'native_fixture_sha256': hashlib.sha256(NATIVE.encode()).hexdigest(),
                          'sources': sorted(files)}, indent=2))
        return
    if not args.kernel or not args.output:
        parser.error('--kernel and --output from a completed --research-owners build are required')
    build(args.kernel.resolve(), args.output.resolve(), args.work.resolve(), args.report.resolve(), args.baseline)


if __name__ == '__main__':
    main()
