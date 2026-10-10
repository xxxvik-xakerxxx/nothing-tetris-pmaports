#!/usr/bin/env python3
"""Close actual prepare-only syscore/sysfs entry points; compile fixtures CI only."""
import argparse
import difflib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'runtime-object-ci'))
from check_objects import load, review

SOURCE = 'drivers/misc/mediatek/eccci/fsm/modem_sys1.c'
ENTRIES = {
    'ccci_modem_syssuspend': '-EOPNOTSUPP',
    'ccci_modem_sysresume': '',
    'ccci_md_attr_show': '-EOPNOTSUPP',
    'ccci_md_attr_store': '-EOPNOTSUPP',
}


def function(source, name):
    pattern = (r'^(?:static )?(?:int|void|ssize_t) ' + re.escape(name) +
               r'\([^;]+?\n\{\n.*?^\}')
    matches = list(re.finditer(pattern, source, re.M | re.S))
    if len(matches) != 1:
        raise ValueError(f'exact-source function drift: {name}')
    return matches[0]


def guard(source, name, result):
    match = function(source, name)
    body = match[0]
    pos = body.index('{\n') + 2
    denial = ('#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)\n'
              '\t/* Preparation does not own physical HIF lifecycle or diagnostics. */\n'
              f'\treturn{(" " + result) if result else ""};\n#endif\n')
    if name.startswith('ccci_md_attr_'):
        callback = 'show' if name.endswith('show') else 'store'
        anchor = f'\tif (a->{callback})'
        if body.count(anchor) != 1:
            raise ValueError(f'dispatch drift: {name}')
        body = body.replace(anchor, '\t(void)kobj;\n' + anchor, 1)
    return source[:match.start()] + body[:pos] + denial + body[pos:] + source[match.end():]


def build(vendor):
    for name in ('runtime-ports', 'runtime-prepare'):
        review(HERE.parent / name)
    prepare = load('lifecycle_complete_prepare', HERE.parent / 'runtime-prepare/check_prepare.py')
    generated, _, files = prepare.build(vendor)
    if generated != (HERE.parent / 'runtime-prepare/runtime-prepare.patch.vendor').read_text():
        raise ValueError('complete-stack prepare differs from frozen review')
    old = files[SOURCE]
    new = old
    for name, result in ENTRIES.items():
        new = guard(new, name, result)
    patch = f'diff --git a/{SOURCE} b/{SOURCE}\n' + ''.join(difflib.unified_diff(
        old.splitlines(True), new.splitlines(True), fromfile='a/' + SOURCE, tofile='b/' + SOURCE))
    return patch, old, new


def apply_check(patch, old):
    with tempfile.TemporaryDirectory(prefix='lifecycle-apply-') as temp:
        root = Path(temp)
        source = root / SOURCE
        source.parent.mkdir(parents=True)
        source.write_text(old)
        subprocess.run(['git', 'apply', '--check', '-'], input=patch, text=True,
                       cwd=root, check=True)


def native_ci(source):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('native C compilation is GitHub CI-only')
    functions = '\n\n'.join(function(source, name)[0] for name in ENTRIES)
    fixture = (HERE / 'test_callbacks.c').read_text().replace('/* PRODUCTION */', functions)
    with tempfile.TemporaryDirectory(prefix='lifecycle-native-') as temp:
        root = Path(temp)
        unit = root / 'callbacks.c'
        unit.write_text(fixture)
        for enabled in (0, 1):
            binary = root / f'callbacks-{enabled}'
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                f'-DCONFIG_MTK_ECCCI_TETRIS_OWNER={enabled}', str(unit),
                '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--native-ci', action='store_true')
    args = parser.parse_args()
    patch, old, new = build(args.vendor)
    if patch != (HERE / 'runtime-lifecycle.patch.vendor').read_text():
        raise ValueError('generated lifecycle overlay differs from review')
    apply_check(patch, old)
    print('Complete-stack lifecycle overlay source/apply PASS; no activation')
    if args.native_ci:
        native_ci(new)


if __name__ == '__main__':
    main()
