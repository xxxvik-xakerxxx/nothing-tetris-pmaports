#!/usr/bin/env python3
"""Emit exact B4.1 integration diff; C fault fixtures run only with --native-ci."""
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "ee2be53cb75670b548948636a0db1d1ff112bf12"
ROOT = "drivers/misc/mediatek/eccci/"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"source drift: {old[:80]!r}")
    return text.replace(old, new, 1)


def integration(tree):
    def original(path):
        return subprocess.check_output(
            ["git", "-C", str(tree), "show", f"{PIN}:{ROOT}{path}"], text=True
        )

    changes = {}
    path = "fsm/md_sys1_platform.c"
    old = original(path)
    new = replace_once(old, "static int ccci_modem_probe(struct platform_device *plat_dev)",
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '#include <linux/sizes.h>\n#include "ccci_tetris_dependencies.h"\n#endif\n\n'
        'static int ccci_modem_probe(struct platform_device *plat_dev)')
    new = replace_once(new, "\t/* Allocate modem hardware info structure memory */",
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tret = tetris_ccci_dependencies(plat_dev);\n'
        '\tif (ret)\n\t\treturn ret;\n#endif\n\n'
        '\t/* Allocate modem hardware info structure memory */')
    changes[path] = (old, new)
    path = "ccci_core.c"
    old = original(path)
    new = replace_once(old, "int ccci_register_dev_node(const char *name, int major_id, int minor)",
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '#include "ccci_tetris_char_node.h"\n#endif\n\n'
        'int ccci_register_dev_node(const char *name, int major_id, int minor)')
    changes[path] = (old, new)
    path = "port/port_t.h"
    old = original(path)
    new = replace_once(old, "\tspinlock_t flag_lock;\n};",
        '\tspinlock_t flag_lock;\n#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tstruct cdev *owned_cdev;\n#endif\n};')
    new = replace_once(new, "struct port_t;", 'struct port_t;\n'
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        'struct cdev;\nstruct file_operations;\n'
        'int ccci_tetris_publish_char(struct cdev **, const struct file_operations *,\n'
        '\t\t\t    const char *, dev_t);\n'
        'void ccci_tetris_unpublish_char(struct cdev **, dev_t);\n#endif')
    changes[path] = (old, new)
    path = "port/port_char.c"
    old = original(path)
    new = replace_once(old, '\tstruct cdev *dev = NULL;',
        '#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\tstruct cdev *dev = NULL;\n#endif')
    new = replace_once(new, '\t\tdev = kmalloc(sizeof(struct cdev), GFP_KERNEL);',
        '#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
        '\t\tret = ccci_tetris_publish_char(&port->owned_cdev, &char_dev_fops,\n'
        '\t\t\tport->name, MKDEV(port->major, port->minor_base + port->minor));\n'
        '\t\tif (ret)\n\t\t\treturn ret;\n#else\n'
        '\t\tdev = kmalloc(sizeof(struct cdev), GFP_KERNEL);')
    new = replace_once(new, '\t\tport->flags |= PORT_F_ADJUST_HEADER;',
        '#endif\n\t\tport->flags |= PORT_F_ADJUST_HEADER;')
    changes[path] = (old, new)
    changes['fsm/ccci_tetris_dependencies.h'] = ('', (HERE / 'ccci_tetris_dependencies.h').read_text())
    changes['ccci_tetris_char_node.h'] = ('', (HERE / 'ccci_tetris_char_node.h').read_text())
    result = []
    for path, (old, new) in changes.items():
        name = ROOT + path
        result.append(f'diff --git a/{name} b/{name}\n')
        if not old:
            result.append('new file mode 100644\n')
        result.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile=f'a/{name}' if old else '/dev/null', tofile=f'b/{name}'))
    return ''.join(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--emit-patch', type=Path)
    parser.add_argument('--native-ci', action='store_true')
    args = parser.parse_args()
    patch = integration(args.vendor)
    if args.emit_patch:
        args.emit_patch.write_text(patch)
    print('source-derived patch SHA256', hashlib.sha256(patch.encode()).hexdigest())
    if not args.native_ci:
        print('C fixtures NOT RUN (CI-only)')
        return
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for component in ('dependencies', 'char_node'):
            production = (HERE / f'ccci_tetris_{component}.h').read_text()
            production = '\n'.join(line for line in production.splitlines()
                                   if not line.startswith('#include '))
            fixture = (HERE / f'test_{component}.c').read_text()
            source = work / f'{component}.c'
            source.write_text(fixture.replace('/* PRODUCTION */', production))
            binary = work / component
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
