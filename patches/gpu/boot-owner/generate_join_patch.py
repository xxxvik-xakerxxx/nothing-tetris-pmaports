#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render a source-pinned owner integration delta; never modify existing owners."""
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def render(root=ROOT):
    pins = json.loads((HERE / 'SOURCE-PINS.json').read_text())['sources']
    sources = {path: (root / path).read_text() for path in pins}
    for path, source in sources.items():
        if hashlib.sha256(source.encode()).hexdigest() != pins[path]:
            raise ValueError('owner source changed; reconcile: ' + path)
    changed = dict(sources)
    edits = {
        'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c': [
            ('module_platform_driver(flat_driver);', (HERE / 'flat-input.inc').read_text().rstrip() + '\n\n' +
             'module_platform_driver(flat_driver);')],
        'patches/gpu/sram-owner/mt6878-gpueb-sram.c': [
            ('#include "mt6878-gpueb-sram.h"', '#include <linux/unaligned.h>\n'
             '#include "mt6878-gpueb-reset.h"\n#include "mt6878-gpueb-sram.h"'),
            ('MODULE_LICENSE("GPL");', (HERE / 'sram-install.inc').read_text().rstrip() + '\n\n' + 'MODULE_LICENSE("GPL");')],
        'patches/gpu/sram-owner/mt6878-gpueb-sram.h': [
            ('struct device;', 'struct platform_device;\nstruct mt6878_gpueb_reset;\nstruct device;'),
            ('#endif', '/* Synchronous private snapshot loan and quarantined reset-held install only. */\n'
             'int tetris_gpueb_flat_use_primary(struct platform_device *input,\n'
             '\t\tint (*consume)(const unsigned char *, unsigned int, void *), void *data);\n'
             'int mt6878_gpueb_sram_install_retained(struct mt6878_gpueb_sram *sram,\n'
             '\t\tstruct mt6878_gpueb_reset *reset, struct platform_device *source);\n#endif')],
        'patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c': [
            ('MODULE_LICENSE("GPL");', (HERE / 'reset-install.inc').read_text().rstrip() + '\n\n' + 'MODULE_LICENSE("GPL");')],
        'patches/gpu/reset-owner-draft/mt6878-gpueb-reset.h': [
            ('struct mt6878_gpueb_sram;', 'struct mt6878_gpueb_window;\nstruct mt6878_gpueb_sram;'),
            ('int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope);',
             'int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope);\n'
             'int mt6878_gpueb_reset_primary_transaction(struct mt6878_gpueb_reset *scope,\n'
             '\t\tstruct mt6878_gpueb_sram *sram,\n'
             '\t\tint (*install)(struct mt6878_gpueb_window *, struct mt6878_gpueb_window *, void *),\n'
             '\t\tvoid *data);')],
    }
    for path, replacements in edits.items():
        for old, new in replacements:
            if changed[path].count(old) != 1:
                raise ValueError('ambiguous integration anchor: ' + path)
            changed[path] = changed[path].replace(old, new, 1)
    patch = ''.join(''.join(unified_diff(sources[path].splitlines(keepends=True),
                                       changed[path].splitlines(keepends=True),
                                       fromfile='a/' + path, tofile='b/' + path)) for path in edits)
    return patch, {path: changed[path] for path in edits}


if __name__ == '__main__':
    try:
        sys.stdout.write(render()[0])
    except (OSError, ValueError) as error:
        sys.exit(str(error))
