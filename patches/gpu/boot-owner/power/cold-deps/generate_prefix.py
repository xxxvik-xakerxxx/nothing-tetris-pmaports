#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render an alternative MFG0-only staged prefix; frozen batches are read-only."""
from difflib import unified_diff
from pathlib import Path
import sys
from audit_cold import HERE, ROOT, PINS, require, sha

NATIVE = 'drivers/pmdomain/mediatek/mtk-pm-domains.c'
RESEARCH = 'drivers/soc/mediatek/tetris-owner-smoke/'
INCLUDE = '#include <linux/soc/mediatek/mt6878-gpueb-cold-prefix.h>\n'
SOURCE = 'patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.c'


def replace(text, old, new):
    require(text.count(old) == 1, 'ambiguous prefix anchor: ' + old[:70])
    return text.replace(old, new, 1)


def native_variant(text):
    require(sha(text.encode()) == PINS['native_prepared_sha256'], 'native packaged source drift')
    text = replace(text, '#include <linux/clk.h>\n', '#include <linux/export.h>\n' + INCLUDE + '#include <linux/clk.h>\n')
    anchor = 'static struct\ngeneric_pm_domain *scpsys_add_one_domain'
    return replace(text, anchor, (HERE / 'native-prefix.inc').read_text().rstrip() + '\n\n' + anchor)


def diff(path, before, after):
    return ''.join(unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                fromfile='a/' + path if before else '/dev/null', tofile='b/' + path))


def render():
    data = (ROOT / SOURCE).read_bytes()
    require(sha(data) == PINS['mfg0_source_sha256'], 'original MFG0 supplier drift')
    old = data.decode()
    new = replace(old, '#include <linux/device.h>', INCLUDE.rstrip() + '\n#include <linux/device.h>')
    new = replace(new, '\tret = mfg0_domain(dev);\n\tif (ret)\n\t\tgoto unlock;',
                   '\tret = mfg0_domain(dev);\n\tif (ret)\n\t\tgoto unlock;\n'
                   '\tret = mt6878_cold_mfg0_preflight(dev);\n\tif (ret)\n\t\tgoto unlock;')
    new = replace(new, '\tif (!pm_runtime_active(dev))\n'
                   '\t\treturn mt6878_gpueb_mfg0_quarantine(scope, -EHOSTDOWN);\n\treturn 0;',
                   '\tif (!pm_runtime_active(dev))\n'
                   '\t\treturn mt6878_gpueb_mfg0_quarantine(scope, -EHOSTDOWN);\n'
                   '\tret = mt6878_cold_mfg0_readback(dev);\n'
                   '\treturn ret ? mt6878_gpueb_mfg0_quarantine(scope, ret) : 0;')
    new = replace(new, '\t*slot = NULL;', '\tif (scope->attempted) {\n'
                   '\t\t/* Retain actual native PM ownership without claiming GPUEB boot. */\n'
                   '\t\tscope->task = NULL;\n\t\tdevice_unlock(dev);\n\t\treturn 0;\n\t}\n\t*slot = NULL;')
    files = {RESEARCH + 'mt6878-gpueb-mfg0.c': new}
    header_path = ROOT / 'patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.h'
    header = header_path.read_bytes()
    require(sha(header) == PINS['mfg0_header_sha256'], 'original MFG0 header drift')
    new_header = replace(header.decode(), 'int mt6878_gpueb_mfg0_finish(',
                         '/* MFG0-only prefix variant: successful attempted resume is retained.\n'
                         ' * finish unlocks the task mutex but leaves *slot and the real PM lease.\n'
                         ' * No firmware/reset/RPC continuation is provided by this variant.\n */\n'
                         'int mt6878_gpueb_mfg0_finish(')
    files[RESEARCH + 'mt6878-gpueb-mfg0.h'] = new_header
    include = '#include <linux/clk.h>\n'
    patch = diff(NATIVE, include, '#include <linux/export.h>\n' + INCLUDE + include)
    anchor = 'static struct\ngeneric_pm_domain *scpsys_add_one_domain(struct scpsys *scpsys, struct device_node *node)\n'
    patch += diff(NATIVE, anchor, (HERE / 'native-prefix.inc').read_text().rstrip() + '\n\n' + anchor)
    patch += diff(RESEARCH + 'mt6878-gpueb-mfg0.c', old, new)
    patch += diff(RESEARCH + 'mt6878-gpueb-mfg0.h', header.decode(), new_header)
    for name in ('mt6878-gpueb-cold-prefix.c', 'mt6878-gpueb-cold-prefix.h'):
        files[RESEARCH + name] = (HERE / name).read_text()
    files['include/linux/soc/mediatek/mt6878-gpueb-cold-prefix.h'] = (HERE / 'mt6878-gpueb-cold-prefix.h').read_text()
    patch += ''.join(diff(path, '', text) for path, text in files.items()
                     if not path.endswith(('mfg0.c', 'mfg0.h')))
    return patch, files


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        (HERE / 'native-prefix.patch').write_text(render()[0])
    elif sys.argv[1:] == ['--check']:
        require((HERE / 'native-prefix.patch').read_text() == render()[0], 'generated prefix patch stale')
        print('source-pinned MFG0-only prefix matches; no activation')
    elif not sys.argv[1:]:
        sys.stdout.write(render()[0])
    else:
        sys.exit('usage: generate_prefix.py [--check|--write]')
