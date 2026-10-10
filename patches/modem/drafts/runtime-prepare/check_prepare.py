#!/usr/bin/env python3
"""Exact-source overlay generator. No C builds without explicit --native-ci."""
import argparse
import difflib
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PIN = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
ROOT = 'drivers/misc/mediatek/eccci/'


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'exact-source drift: {old[:100]!r}')
    return source.replace(old, new, 1)


def overlay(files, patch):
    """Apply exact-context unified hunks in memory; reject fuzz and offsets."""
    sections = patch.split('diff --git ')[1:]
    for section in sections:
        lines = section.splitlines(True)
        path = lines[0].split()[1][2:]
        original = files.get(path, '').splitlines(True)
        result, cursor = [], 0
        index = 1
        while index < len(lines):
            match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[index])
            if not match:
                index += 1
                continue
            start = max(0, int(match[1]) - 1)
            result.extend(original[cursor:start])
            cursor = start
            index += 1
            while index < len(lines) and not lines[index].startswith('@@ '):
                line = lines[index]
                if line.startswith((' ', '-')):
                    if cursor >= len(original) or original[cursor] != line[1:]:
                        raise ValueError(f'overlay drift {path}:{cursor + 1}')
                    cursor += 1
                if line.startswith((' ', '+')):
                    result.append(line[1:])
                index += 1
        result.extend(original[cursor:])
        files[path] = ''.join(result)


def build(tree):
    names = ['fsm/ccci_fsm.c', 'fsm/modem_sys1.c', 'fsm/md_sys1_platform.c',
             'fsm/ccci_fsm_poller.c', 'fsm/ccci_fsm_monitor.c',
             'port/port_t.h', 'port/port_proxy.c', 'port/port_cfg.c',
             'port/port_char.c', 'port/port_ctlmsg.c', 'port/port_sysmsg.c',
             'port/port_udc.c', 'port/port_ipc.c', 'port/port_rpc.c',
             'port/port_smem.c', 'port/port_net.c', 'ccci_core.c']
    names += ['hif/ccci_hif_ccif.c', 'hif/ccci_dpmaif_com.c', 'fsm/ccci_fsm_ioctl.c']
    owner_spec = importlib.util.spec_from_file_location('complete_owner',
        HERE.parents[1] / 'check_transport_owner.py')
    owner = importlib.util.module_from_spec(owner_spec)
    owner_spec.loader.exec_module(owner)
    owner_bundle = owner.bundle()
    paths = set(ROOT + name for name in names)
    paths.update(re.findall(r'^diff --git a/(\S+) b/', owner_bundle, re.M))
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for path in sorted(paths - owner.NEW.keys()):
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(
                ['git', '-C', str(tree), 'show', f'{PIN}:{path}']))
        power = owner.first.power
        saved = power.FILES.copy()
        power.FILES.clear()
        power.FILES.update(paths)
        try:
            patches = re.findall(r'^\s+([\w.-]+\.patch\.vendor)$',
                (power.PACKAGE / 'APKBUILD').read_text(), re.M)
            for name in dict.fromkeys(patches):
                selected = ''.join(power.sections((power.PACKAGE / name).read_text(encoding='latin-1')))
                if selected:
                    owner.apply_patch(work, selected)
        finally:
            power.FILES.clear()
            power.FILES.update(saved)
        owner.apply_patch(work, owner_bundle)
        spec = importlib.util.spec_from_file_location('runtime_ports',
            HERE.parent / 'runtime-ports/check_runtime_ports.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        owner.apply_patch(work, module.integration(tree))
        files = {str(path.relative_to(work)): path.read_text()
                 for path in sorted(work.rglob('*')) if path.is_file()}
    before = dict(files)
    core = ROOT + 'ccci_core.c'
    anchor = '\tdev_class = class_create("ccci_node");'
    if files[core].count(anchor) != 2:
        raise ValueError('drift in both actual CCCI class initialization branches')
    files[core] = files[core].replace(anchor, anchor +
        '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tif (IS_ERR(dev_class))\n\t\treturn PTR_ERR(dev_class);\n#endif')

    def edit(name, old, new):
        path = ROOT + name
        files[path] = replace(files[path], old, new)

    def include(name, anchor, header):
        edit(name, anchor, '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
             f'#include "ccci_tetris_prepare.h"\n#include "{header}"\n#endif\n\n' + anchor)

    include('fsm/ccci_fsm.c', 'int ccci_fsm_init(void)', 'fsm_prepare.h')
    edit('fsm/ccci_fsm.c', '#include "ccci_fsm_sys.h"',
         '#include "ccci_fsm_sys.h"\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '#include "ccci_tetris_prepare.h"\n#endif')
    edit('fsm/ccci_fsm.c', '\tint ret = 0;\n\n\tctl = kzalloc(sizeof(struct ccci_fsm_ctl), GFP_KERNEL);',
         '\tint ret = 0;\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t/* Only the prepared common registration caller owns this path. */\n'
         '\treturn -EPERM;\n#endif\n\n'
         '\tctl = kzalloc(sizeof(struct ccci_fsm_ctl), GFP_KERNEL);')
    include('port/port_proxy.c', 'static inline void proxy_init_all_ports(struct port_proxy *proxy_p)',
            'ports_prepare.h')
    edit('port/port_proxy.c', 'int ccci_port_init(void)',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         'static struct proc_dir_entry *tetris_dbm_proc;\n'
         'int ccci_tetris_proc_publish(void)\n{\n'
         '\tspin_lock_init(&file_lock);\n'
         '\ttetris_dbm_proc = proc_create("ccci_lp_mem", 0440, NULL, &ccci_dbm_ops);\n'
         '\treturn tetris_dbm_proc ? 0 : -ENOMEM;\n}\n#endif\n\n'
         'int ccci_port_init(void)')
    edit('port/port_proxy.c', '\t\treturn -1;\n\t}\n\treturn 0;\n}\n\nstatic void port_dump_net',
         '\t\treturn -ENOMEM;\n\t}\n\treturn 0;\n}\n\nstatic void port_dump_net')
    edit('port/port_t.h', '\tstruct cdev *owned_cdev;',
         '\tstruct cdev *owned_cdev;\n\tstruct task_struct *owned_worker;')
    edit('port/port_t.h', 'struct port_t;',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '#include "ccci_tetris_prepare.h"\n#endif\nstruct port_t;')
    include('fsm/modem_sys1.c', 'int ccci_modem_init_common(struct platform_device *plat_dev,',
            'register_prepare.h')
    edit('fsm/modem_sys1.c', '\t/* init per-modem sub-system */',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t/* The legacy entry cannot bypass transactional common preparation. */\n'
         '\treturn -EPERM;\n#endif\n\t/* init per-modem sub-system */')
    edit('fsm/modem_sys1.c', '\t/* Allocate md ctrl memory and do initialize */',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\treturn tetris_common_prepare(plat_dev, dev_cfg, md_hw);\n#endif\n\n'
         '\t/* Allocate md ctrl memory and do initialize */')
    edit('fsm/md_sys1_platform.c', '#include "ccci_tetris_dependencies.h"',
         '#include "ccci_tetris_dependencies.h"\n#include "ccci_tetris_prepare.h"')
    edit('fsm/md_sys1_platform.c', '\tif (ret < 0) {\n\t\tkfree(md_hw);\n\t}',
         '\tif (ret < 0) {\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t\t/* Published callbacks may retain md->hw_info on partial failure. */\n'
         '\t\tif (!ccci_tetris_registration_retained())\n#endif\n'
         '\t\t\tkfree(md_hw);\n\t}')
    edit('fsm/md_sys1_platform.c', '#ifdef CCCI_KMODULE_ENABLE\n\tccci_init();\n#endif',
         '#if defined(CCCI_KMODULE_ENABLE) && !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tccci_init();\n#endif')
    path = ROOT + 'fsm/md_sys1_platform.c'
    for name in ('ccci_modem_pm_suspend', 'ccci_modem_pm_resume', 'ccci_modem_pm_restore_noirq'):
        function = re.search(rf'^static int {name}\([^;]+?\n\{{', files[path], re.M | re.S)
        if not function:
            raise ValueError(f'missing actual PM entry {name}')
        position = function.end()
        files[path] = files[path][:position] + '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n' + \
            '\treturn -EOPNOTSUPP;\n#endif' + files[path][position:]
    edit('fsm/md_sys1_platform.c', '#ifdef USING_PM_RUNTIME\n\tpm_runtime_enable(&dev_ptr->dev);',
         '#if defined(USING_PM_RUNTIME) && !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tpm_runtime_enable(&dev_ptr->dev);')
    edit('fsm/md_sys1_platform.c', '\t\t\tclk_table[idx].clk_ref = NULL;',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t\t\treturn PTR_ERR(clk_table[idx].clk_ref);\n#endif\n'
         '\t\t\tclk_table[idx].clk_ref = NULL;')
    edit('fsm/md_sys1_platform.c', '\t\t\t"ccci-spmsleep");\n\tif (IS_ERR(md_cd_plat_val_ptr.spm_sleep_base))',
         '\t\t\t"ccci-spmsleep");\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tif (IS_ERR(md_cd_plat_val_ptr.spm_sleep_base))\n'
         '\t\treturn PTR_ERR(md_cd_plat_val_ptr.spm_sleep_base);\n#endif\n'
         '\tif (IS_ERR(md_cd_plat_val_ptr.spm_sleep_base))')
    # Resource-only probe has no surviving callbacks on either failure return.
    path = ROOT + 'fsm/md_sys1_platform.c'
    helper = '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
    helper += 'static void tetris_hw_abort(struct md_hw_info *hw)\n{\n'
    helper += '\tif (hw->md_l2sram_base)\n\t\tiounmap(hw->md_l2sram_base);\n'
    helper += '\tif (hw->sequencer_base)\n\t\tiounmap(hw->sequencer_base);\n'
    helper += '\t/* OF IRQ mapping may pre-exist; no exclusive ownership proof to dispose it. */\n'
    helper += '}\n#endif\n\n'
    files[path] = replace(files[path], 'static int ccci_modem_probe(struct platform_device *plat_dev)',
        helper + 'static int ccci_modem_probe(struct platform_device *plat_dev)')
    edit('fsm/md_sys1_platform.c', '\t\tkfree(md_hw);\n\t\treturn -1;',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t\ttetris_hw_abort(md_hw);\n\t\tkfree(md_hw);\n\t\treturn ret;\n#else\n'
         '\t\tkfree(md_hw);\n\t\treturn -1;\n#endif')
    edit('fsm/md_sys1_platform.c', '\t\t/* Published callbacks may retain md->hw_info on partial failure. */',
         '\t\ttetris_hw_abort(md_hw);\n'
         '\t\t/* This path failed only unpublished resource preparation. */')
    for name, anchor in (('fsm/md_sys1_platform.c', '.name = "driver_modem",'),
                         ('hif/ccci_hif_ccif.c', '.name = "ccci_hif_ccif",'),
                         ('hif/ccci_dpmaif_com.c', '.name = "ccci_dpmaif_driver",')):
        if ROOT + name not in files:
            text = subprocess.check_output(['git', '-C', str(tree), 'show',
                f'{PIN}:{ROOT}{name}'], text=True)
            files[ROOT + name] = before[ROOT + name] = text
        edit(name, anchor, anchor + '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
             '\t\t.suppress_bind_attrs = true,\n#endif')

    # Preserve each real handler/private-data ABI, but keep every worker parked.
    for name in ('port_ctlmsg.c', 'port_sysmsg.c', 'port_udc.c'):
        path = ROOT + 'port/' + name
        text = files[path]
        match = re.search(r'port->private_data = kthread_run\(port_kthread_handler,\s*port, "%s",\s*port->name\);', text)
        if not match:
            raise ValueError(f'missing actual worker {name}')
        replacement = '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        replacement += '\tport->private_data = ccci_tetris_port_worker(port, port_kthread_handler);\n'
        replacement += '\tif (IS_ERR(port->private_data))\n\t\treturn PTR_ERR(port->private_data);\n#else\n\t'
        replacement += match[0] + '\n#endif'
        files[path] = replace(text, match[0], replacement)
    edit('port/port_sysmsg.c', '\tswtp_init();',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t{\n\t\tint ret = swtp_init();\n\t\tif (ret)\n\t\t\treturn ret;\n\t}\n#else\n'
         '\tswtp_init();\n#endif')
    for name, body in (('port_ipc.c', 'port_ipc_kernel_thread'), ('port_rpc.c', 'port_kthread_handler')):
        edit('port/' + name, f'kthread_run({body}, port, "%s", port->name);',
             '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
             f'\t\tstruct task_struct *worker = ccci_tetris_port_worker(port, {body});\n'
             '\t\tif (IS_ERR(worker))\n\t\t\treturn PTR_ERR(worker);\n#else\n'
             f'\t\tkthread_run({body}, port, "%s", port->name);\n#endif')

    # Reuse actual fops for every char-bearing kind; no alternate channels.
    for name, fops in (('port_ipc.c', 'ipc_dev_fops'), ('port_rpc.c', 'rpc_dev_fops'),
                       ('port_smem.c', 'smem_dev_fops')):
        path = ROOT + 'port/' + name
        text = files[path]
        start = text.index('\t\tdev = kmalloc(sizeof(struct cdev), GFP_KERNEL);')
        end = text.index('\t\tport->interception = 0;', start) if name != 'port_rpc.c' else text.index('\t\tport->flags |= PORT_F_ADJUST_HEADER;', start)
        old = text[start:end]
        new = '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        new += f'\t\tret = ccci_tetris_publish_char(&port->owned_cdev, &{fops},\n'
        new += '\t\t\tport->name, MKDEV(port->major, port->minor_base + port->minor));\n'
        new += '\t\tif (ret)\n\t\t\treturn ret;\n#else\n' + old + '#endif\n'
        files[path] = replace(text, old, new)
        edit('port/' + name, '\tstruct cdev *dev = NULL;',
             '#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n\tstruct cdev *dev = NULL;\n#endif')

    edit('port/port_net.c', '\t\tccmni_ops.init(&eccci_ccmni_ops);',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t\treturn ccmni_ops.init(&eccci_ccmni_ops);\n#else\n'
         '\t\tccmni_ops.init(&eccci_ccmni_ops);\n#endif')
    edit('fsm/ccci_fsm_poller.c', '\treturn 0;\n}\n\n\nint ccci_fsm_recv_status_packet',
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tif (IS_ERR(poller_ctl->poll_thread))\n\t\treturn PTR_ERR(poller_ctl->poll_thread);\n'
         '#endif\n\treturn 0;\n}\n\n\nint ccci_fsm_recv_status_packet')
    # Preserve first monitor failure; partial legacy publication is retained.
    for anchor in ('"alloc_chrdev_region fail, ret=%d\\n", ret);',
                   '"cdev_add fail, ret=%d\\n", ret);'):
        edit('fsm/ccci_fsm_monitor.c', anchor,
             anchor + '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
             '\tif (ret)\n\t\treturn ret;\n#endif')

    # Monitor cannot be used as a control backdoor, even after registration.
    for name in ('dev_char_open', 'dev_char_close', 'dev_char_ioctl', 'dev_char_compat_ioctl'):
        path = ROOT + 'fsm/ccci_fsm_monitor.c'
        function = re.search(rf'^static (?:int|long) {name}\([^;]+?\n\{{', files[path], re.M | re.S)
        if not function:
            raise ValueError(f'missing monitor boundary {name}')
        position = function.end()
        guard = '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        guard += '\t/* Prepare-only monitor never owns physical control operations. */\n'
        guard += '\treturn -EOPNOTSUPP;\n#endif'
        files[path] = files[path][:position] + guard + files[path][position:]
    path = ROOT + 'fsm/ccci_fsm_ioctl.c'
    function = re.search(r'^(?:int|long) ccci_fsm_ioctl\([^;]+?\n\{', files[path], re.M | re.S)
    if not function:
        raise ValueError('missing actual ccci_fsm_ioctl entry')
    position = function.end()
    files[path] = files[path][:position] + '\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n' + \
        '\treturn -EOPNOTSUPP;\n#endif' + files[path][position:]

    # Fail closed for char opens on partial registration. No AT/GSM policy.
    edit('port/port_proxy.c', 'int port_dev_open(struct inode *inode, struct file *file)\n{',
         'int port_dev_open(struct inode *inode, struct file *file)\n{\n'
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tif (!ccci_tetris_registration_complete())\n\t\treturn -ENODEV;\n#endif')
    edit('port/port_proxy.c', '\tatomic_dec(&port->usage_cnt);\n\t/* 1. purge Rx request list */',
         '#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tatomic_dec(&port->usage_cnt);\n#endif\n\t/* 1. purge Rx request list */')
    edit('port/port_proxy.c', '\tport_user_unregister(port);\n\n\treturn 0;',
         '\tport_user_unregister(port);\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\t/* Last callback/HIF access above still owns this file reference.\n'
         '\t * Zero usage is NOT a proof of IRQ/workqueue/DMA drain. */\n'
         '\tfile->private_data = NULL;\n\tatomic_dec(&port->usage_cnt);\n#endif\n\n\treturn 0;')
    edit('port/port_cfg.c', 'int mtk_ccci_open_port(int index)\n{',
         'int mtk_ccci_open_port(int index)\n{\n'
         '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
         '\tif (!ccci_tetris_registration_complete())\n\t\treturn -ENODEV;\n#endif')
    # A registration draft must never execute legacy START/STOP or claim OFF.
    for routine in ('start', 'stop'):
        path = ROOT + 'fsm/ccci_fsm.c'
        start = files[path].index(f'static void fsm_routine_{routine}(')
        anchor = ('#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
                  '\tret = ccci_tetris_owner_entry();') if routine == 'start' else '\t/* 1. state sanity check */'
        position = files[path].index(anchor, start)
        guard = '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        guard += '\t/* No physical stop/start contract is provided by registration. */\n'
        guard += '\tccci_tetris_registration_quarantine(-EOPNOTSUPP);\n'
        guard += '\tfsm_finish_command(ctl, cmd, -1);\n\treturn;\n#endif\n'
        files[path] = files[path][:position] + guard + files[path][position:]

    for name in ('ccci_tetris_prepare.h', 'fsm_prepare.h', 'ports_prepare.h', 'register_prepare.h'):
        dest = 'port/' if name == 'ports_prepare.h' else 'fsm/'
        if name == 'ccci_tetris_prepare.h':
            dest = 'inc/'
        files[ROOT + dest + name] = (HERE / name).read_text()
    result = []
    for path, new in sorted(files.items()):
        old = before.get(path, '')
        if old == new:
            continue
        result.append(f'diff --git a/{path} b/{path}\n')
        if not old:
            result.append('new file mode 100644\n')
        result.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile=f'a/{path}' if old else '/dev/null', tofile=f'b/{path}'))
    return ''.join(result), before, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--emit-patch', type=Path)
    parser.add_argument('--native-ci', action='store_true')
    args = parser.parse_args()
    patch, before, _ = build(args.vendor)
    if args.emit_patch:
        args.emit_patch.write_text(patch)
    print('Exact pinned source + packaged adaptations + frozen owner + runtime-ports: PASS')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        for name, source in before.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
        subprocess.run(['git', 'apply', '--check', '-'], input=patch, text=True,
                       cwd=path, check=True)
    print('Static git apply check on complete packaged+owner+runtime-ports stack: PASS')
    if args.native_ci:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name in ('fsm', 'ports', 'registration'):
                header = 'register_prepare.h' if name == 'registration' else f'{name}_prepare.h'
                production = '\n'.join(line for line in (HERE / header).read_text().splitlines()
                    if not line.startswith('#include '))
                source = (HERE / f'test_{name}.c').read_text().replace(
                    '/* PRODUCTION */', production)
                unit = path / f'{name}.c'
                unit.write_text(source)
                binary = path / name
                subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(unit), '-o', str(binary)], check=True)
                subprocess.run([str(binary)], check=True)
    else:
        print('Native C NOT RUN (CI only)')


if __name__ == '__main__':
    main()
