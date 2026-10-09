#!/usr/bin/env python3
"""Source checks locally; production C with mock boundaries only on CI."""
import argparse
import difflib
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>
#define EPROBE_DEFER 517
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;
typedef uint64_t resource_size_t;
struct resource { resource_size_t start, end; unsigned long flags; };
struct bus_type { int identity; };
static struct bus_type platform_bus_type;
#define IORESOURCE_MEM 0x200
static struct resource supplier_resource = {0x1c00f000, 0x1c00ffff, IORESOURCE_MEM};
struct arm_smccc_res { unsigned long a0, a1, a2, a3; };
struct module { int pins; bool available; };
struct device_driver { int identity; };
struct device {
    struct device_driver *driver;
    void *data;
    int refs;
    pthread_mutex_t lock;
    struct bus_type *bus;
};
struct platform_device { struct device dev; };
#define to_platform_device(d) ((struct platform_device *)(d))
static struct resource *platform_get_resource(struct platform_device *p,
                                              unsigned int type, unsigned int index) {
    assert(p && type == IORESOURCE_MEM && index == 0);
    return &supplier_resource;
}
struct task_struct { int identity; };
static _Thread_local struct task_struct task;
#define current (&task)
#define DEFINE_MUTEX(name) pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
#define mutex_lock(m) assert(pthread_mutex_lock(m) == 0)
#define mutex_unlock(m) assert(pthread_mutex_unlock(m) == 0)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_ACQUIRE)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x), (v), __ATOMIC_RELEASE)
#define EXPORT_SYMBOL_GPL(x)
#define MODULE_LICENSE(x)
#define check_add_overflow(a,b,out) __builtin_add_overflow(a,b,out)
static struct device *get_device(struct device *d) {
    if (d)
        __atomic_add_fetch(&d->refs, 1, __ATOMIC_RELAXED);
    return d;
}
static void put_device(struct device *d) {
    assert(__atomic_sub_fetch(&d->refs, 1, __ATOMIC_RELAXED) >= 1);
}
static void device_lock(struct device *d) { mutex_lock(&d->lock); }
static void device_unlock(struct device *d) { mutex_unlock(&d->lock); }
static void *dev_get_drvdata(struct device *d) { return d->data; }
static bool try_module_get(struct module *m) {
    if (m && !m->available)
        return false;
    if (m)
        m->pins++;
    return true;
}
static void module_put(struct module *m) {
    if (m)
        assert(--m->pins >= 0);
}
static int smc_calls;
static unsigned long smc_status;
static void arm_smccc_smc(unsigned long fid, unsigned long request,
                         unsigned long flags, unsigned long vmode,
                         unsigned long a4, unsigned long a5,
                         unsigned long a6, unsigned long a7,
                         struct arm_smccc_res *result) {
    assert(fid == 0xc2000506 && request == 0);
    assert(flags == 0x12 && vmode == 3 && !a4 && !a5 && !a6 && !a7);
    smc_calls++;
    *result = (struct arm_smccc_res){smc_status, 4, 5, 6};
}
'''

TEST = r'''
static struct device_driver driver = {1}, other_driver = {2};
static struct device dev = {&driver, &driver, 1, PTHREAD_MUTEX_INITIALIZER, &platform_bus_type};
static struct module auth_module = {0, true};
static struct mt6878_md_handoff_state input;
static int snapshot_error, auth_error, authenticated;
static pthread_barrier_t race_ready;
static int snapshot(void *owner, struct mt6878_md_handoff_state *state) {
    assert(owner == &input);
    *state = input;
    return snapshot_error;
}
static int authenticate(void *owner, const struct mt6878_md_handoff_state *state) {
    assert(owner == &input && state->rom_size);
    authenticated++;
    return auth_error;
}
static struct mt6878_md_handoff_owner auth = {&auth_module, snapshot, authenticate};
static void reset(void) {
    assert(!md_scope.task && !auth_module.pins);
    if (md_scope.supplier)
        put_device(md_scope.supplier);
    memset(&md_scope, 0, sizeof(md_scope));
    input = (struct mt6878_md_handoff_state){
        .rom_base = 0x100000, .rom_size = 0x10000,
        .smem_base = 0x200000, .smem_size = 0x20000,
        .rom_digest = {1,2,3},
    };
    dev.driver = &driver;
    dev.data = &driver;
    supplier_resource = (struct resource){0x1c00f000, 0x1c00ffff, IORESOURCE_MEM};
    auth_module.available = true;
    snapshot_error = auth_error = authenticated = smc_calls = 0;
    smc_status = 0;
    assert(dev.refs == 1);
}
static void init(void) {
    struct arm_smccc_res result;
    device_lock(&dev);
    assert(mt6878_md_scoped_dvfsrc_init(&dev, 0x12, 3, &result) == 0);
    device_unlock(&dev);
    assert(result.a0 == smc_status && result.a1 == 4 && result.a2 == 5 && result.a3 == 6);
}
static void *race(void *unused) {
    struct arm_smccc_res result;
    (void)unused;
    assert(mt6878_md_scope_validate_execution() == -EPERM);
    assert(mt6878_md_scope_end(0) == -EPERM);
    assert(pthread_mutex_trylock(&md_scope_lock) == EBUSY);
    int barrier = pthread_barrier_wait(&race_ready);
    assert(barrier == 0 || barrier == PTHREAD_BARRIER_SERIAL_THREAD);
    device_lock(&dev);
    assert(mt6878_md_scoped_dvfsrc_init(&dev, 0x12, 3, &result) == -EBUSY);
    device_unlock(&dev);
    return NULL;
}
int main(void) {
    pthread_t worker;
    int cases = 0;
    reset();
    assert(mt6878_md_scope_begin(NULL, &input) == -ENOKEY);
    assert(mt6878_md_scope_begin(&auth, &input) == -EPROBE_DEFER);
    assert(!smc_calls);
    cases++;
    reset(); init();
    assert(mt6878_md_scope_begin(&auth, &input) == 0);
    assert(mt6878_md_scope_begin(&auth, &input) == -EALREADY);
    assert(mt6878_md_scope_validate_execution() == 0 && authenticated == 2);
    assert(pthread_barrier_init(&race_ready, NULL, 2) == 0);
    assert(pthread_create(&worker, NULL, race, NULL) == 0);
    int barrier = pthread_barrier_wait(&race_ready);
    assert(barrier == 0 || barrier == PTHREAD_BARRIER_SERIAL_THREAD);
    assert(mt6878_md_scope_end(0) == 0);
    assert(pthread_join(worker, NULL) == 0 && smc_calls == 1);
    assert(pthread_barrier_destroy(&race_ready) == 0);
    assert(mt6878_md_scope_begin(&auth, &input) == -EALREADY);
    cases++;
    for (int field = 0; field < 7; field++) {
        reset(); init();
        assert(mt6878_md_scope_begin(&auth, &input) == 0);
        switch (field) {
        case 0: input.rom_base++; break;
        case 1: input.rom_size++; break;
        case 2: input.smem_base++; break;
        case 3: input.smem_size++; break;
        case 4: input.rom_digest[0]++; break;
        case 5: dev.data = &other_driver; break;
        case 6: supplier_resource.start++; break;
        }
        assert(mt6878_md_scope_validate_execution() == -ESTALE);
        auth_error = -EACCES;
        assert(mt6878_md_scope_validate_execution() == -ESTALE);
        assert(mt6878_md_scope_end(-EIO) == -ESTALE && smc_calls == 1);
        cases++;
    }
    for (int fault = 0; fault < 6; fault++) {
        reset(); init();
        int expected;
        switch (fault) {
        case 0: snapshot_error = -EIO; expected = -EIO; break;
        case 1: auth_error = -EACCES; expected = -EACCES; break;
        case 2: auth_error = 1; expected = -EPROTO; break;
        case 3: input.rom_base = UINT64_MAX; expected = -EINVAL; break;
        case 4: input.smem_base = input.rom_base; expected = -EINVAL; break;
        default: auth_module.available = false; expected = -ENODEV; break;
        }
        assert(mt6878_md_scope_begin(&auth, &input) == expected);
        assert(mt6878_md_scope_begin(&auth, &input) == expected);
        assert(!auth_module.pins && dev.refs == 2 && smc_calls == 1);
        cases++;
    }
    reset(); smc_status = 0xffffffff; init();
    assert(mt6878_md_scope_begin(&auth, &input) == -EPROTO);
    assert(md_scope.init_status == 0xffffffff && !authenticated);
    cases++;
    reset();
    assert(mt6878_md_scope_validate_execution() == -EPERM);
    assert(mt6878_md_scope_end(0) == -EPERM);
    printf("PASS %d cases: real scope C, mock SMC/auth/device boundaries only\n", cases);
    return 0;
}
'''


def stripped(path):
    return "\n".join(line for line in path.read_text().splitlines()
                     if not line.startswith("#include"))


def kernel_patch(kernel):
    edits = {}
    name = "drivers/soc/mediatek/Kconfig"
    old = (kernel / name).read_text()
    block = ('config MTK_MT6878_MD_STARTUP_SCOPE\n'
             '\tbool "MT6878 scoped modem startup (compile-only candidate)"\n'
             '\tdepends on ARCH_MEDIATEK && ARM64 && OF\n'
             '\thelp\n'
             '\t  Default off. Serializes selected DVFSRC INIT against first start.\n'
             '\t  Requires a real authenticated handoff owner; does not enable MD.\n\n')
    assert old.endswith("endmenu\n") and "config MTK_MT6878_MD_STARTUP_SCOPE" not in old
    edits[name] = (old, old[:-len("endmenu\n")] + block + "endmenu\n")
    name = "drivers/soc/mediatek/Makefile"
    old = (kernel / name).read_text()
    edits[name] = (old, old + "obj-$(CONFIG_MTK_MT6878_MD_STARTUP_SCOPE) += mt6878_md_startup_scope.o\n")
    name = "drivers/soc/mediatek/mtk-dvfsrc.c"
    old = (kernel / name).read_text()
    include = "#include <linux/soc/mediatek/mtk_sip_svc.h>\n"
    call = ("\tarm_smccc_smc(MTK_SIP_DVFSRC_VCOREFS_CONTROL, MTK_SIP_DVFSRC_INIT,\n"
            "\t\t      0, 0, 0, 0, 0, 0, &ares);\n")
    assert old.count(include) == 1 and old.count(call) == 1
    replacement = ("#if IS_ENABLED(CONFIG_MTK_MT6878_MD_STARTUP_SCOPE)\n"
                   "\tret = mt6878_md_scoped_dvfsrc_init(dvfsrc->dev, 0, 0, &ares);\n"
                   "\tif (ret)\n"
                   "\t\treturn dev_err_probe(&pdev->dev, ret, \"DVFSRC INIT owner rejected\\n\");\n"
                   "#else\n" + call + "#endif\n")
    edits[name] = (old, old.replace(include, include +
                    "#include <linux/soc/mediatek/mt6878_md_startup_scope.h>\n").replace(call, replacement))
    for target, source in (
        ("drivers/soc/mediatek/mt6878_md_startup_scope.c", "mt6878_md_startup_scope.c"),
        ("include/linux/soc/mediatek/mt6878_md_startup_scope.h", "mt6878_md_startup_scope.h"),
    ):
        assert not (kernel / target).exists()
        edits[target] = ("", (HERE / source).read_text())
    result = "Subject: [PATCH] soc: mediatek: default-off scoped MD startup component\n\n"
    for name, (old, new) in edits.items():
        result += f"diff --git a/{name} b/{name}\n"
        if not old:
            result += "new file mode 100644\n"
        result += "".join(difflib.unified_diff(old.splitlines(keepends=True),
                                              new.splitlines(keepends=True),
                                              fromfile=f"a/{name}" if old else "/dev/null",
                                              tofile=f"b/{name}", n=3))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--vendor", type=Path, help="read pinned blobs and check follow-up patch only")
    parser.add_argument("--kernel", type=Path, help="check default-off component patch against pristine kernel")
    parser.add_argument("--emit-kernel", type=Path, help="write deterministic component patch; needs --kernel")
    args = parser.parse_args()
    source = (HERE / "mt6878_md_startup_scope.c").read_text()
    assert source.count("arm_smccc_smc(") == 1
    assert "arm_smccc_smc(0xc2000506, 0, flags, vmode" in source
    assert "auth->snapshot || !auth->authenticate" in source
    assert "memcmp(now.rom_digest" in source
    assert source.index("device_lock(dev);", source.index("int mt6878_md_scope_begin")) < source.index(
        "md_scope.attempted = true;", source.index("int mt6878_md_scope_begin"))
    print("PASS source scope checks; no production auth provider or shipping activation")
    if args.emit_kernel and not args.kernel:
        parser.error("--emit-kernel requires --kernel")
    if args.kernel:
        patch = kernel_patch(args.kernel)
        with tempfile.TemporaryDirectory(prefix="mt6878-md-scope-kernel-") as tmp:
            tree = Path(tmp)
            for name in ("drivers/soc/mediatek/Kconfig", "drivers/soc/mediatek/Makefile",
                         "drivers/soc/mediatek/mtk-dvfsrc.c"):
                target = tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((args.kernel / name).read_bytes())
            patchfile = tree / "component.patch"
            patchfile.write_text(patch)
            subprocess.run(["git", "apply", "--check", str(patchfile)], cwd=tree, check=True)
            subprocess.run(["patch", "--dry-run", "-p1", "-i", str(patchfile)], cwd=tree, check=True)
        if args.emit_kernel:
            args.emit_kernel.write_text(patch)
        print("PASS default-off kernel component apply check")
    if args.vendor:
        pin = "ee2be53cb75670b548948636a0db1d1ff112bf12"
        with tempfile.TemporaryDirectory(prefix="mt6878-md-scope-apply-") as tmp:
            tree = Path(tmp)
            for name in ("drivers/misc/mediatek/eccci/Kconfig", "drivers/soc/mediatek/mtk-dvfsrc.c"):
                target = tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(
                    ["git", "-C", str(args.vendor), "show", f"{pin}:{name}"]))
            subprocess.run(["git", "apply", "--include=drivers/misc/mediatek/eccci/Kconfig",
                            str(HERE / "0007-ccci-first-start-owner.patch.vendor")], cwd=tree, check=True)
            fsm = tree / "drivers/misc/mediatek/eccci/fsm"
            fsm.mkdir()
            for name in ("ccci_tetris_owner.c", "ccci_tetris_owner.h"):
                (fsm / name).write_bytes((HERE / name).read_bytes())
            patch = HERE / "startup-scope-integration.patch.vendor"
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True)
            subprocess.run(["patch", "--dry-run", "-p1", "-i", str(patch)], cwd=tree, check=True)
        print("PASS pinned vendor + frozen canonical owner follow-up apply check")
    if not args.native_ci:
        return
    if os.environ.get("CI") != "true":
        parser.error("native C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="mt6878-md-scope-") as tmp:
        src = Path(tmp) / "scope.c"
        exe = Path(tmp) / "scope"
        src.write_text(PRELUDE + stripped(HERE / "mt6878_md_startup_scope.h") +
                       stripped(HERE / "mt6878_md_startup_scope.c") + TEST)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        "-pthread", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
