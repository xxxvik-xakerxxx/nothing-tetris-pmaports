#!/usr/bin/env python3
"""Generate/apply-check the resource-only overlay on the complete pinned stack."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VENDOR = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
LINUX = 'd84b264a54a37611f2f46bc19363cb9b41606205'
BASELINE = 'e0c67c561ff7c1a0472da851edfafd5a0abb6cec'
PREFIX = 'drivers/misc/mediatek/'
ECCCI = PREFIX + 'eccci/'
GUARD = '#if IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n'
PAYLOADS = {'resources.h': 'inc/tetris_hif_resources.h',
            'supplier.h': 'hif/tetris_hif_supplier.h',
            'consumer.h': 'fsm/tetris_hif_consumer.h',
            'modem.h': 'fsm/tetris_modem_resources.h'}
CENSUS = {
    'ccci_md_all': ('eccci/fsm/md_sys1_platform.c', 'modem_cd_init', 'ccci_modem_probe', 'mediatek,mddriver'),
    'ccci_auxadc': ('eccci/ccci_auxadc.c', 'ccci_auxadc_init', 'get_auxadc_probe', 'mediatek,md_auxadc'),
    'ccci_ccif': ('eccci/hif/ccci_hif_ccif.c', 'ccci_hif_ccif_init', 'ccci_hif_ccif_probe', 'mediatek,ccci_ccif'),
    'ccci_dpmaif': ('eccci/hif/ccci_dpmaif_com.c', 'ccci_dpmaif_init', 'dpmaif_probe', 'mediatek,dpmaif'),
    'ccci_cldma': ('eccci/hif/ccci_hif_cldma.c', 'ccci_cldma_init', 'ccci_hif_cldma_probe', 'mediatek,ccci_cldma'),
    'ccci_fsm_scp': ('eccci/fsm/ccci_fsm_scp_c.c', 'ccci_scp_init', 'ccci_scp_probe', 'mediatek,ccci_md_scp'),
    'ccmni': ('ccmni/ccmni.c', None, None, None),
    'rps_perf': ('rps/rps_perf.c', None, None, None),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('exact resource source drift: ' + repr(old[:100]))
    return source.replace(old, new, 1)


def function(source, name):
    pattern = r'^(?:static )?(?:inline )?(?:int|void) (?:__init |__exit )?' + re.escape(name) + r'\([^;]+?\n\{\n.*?^\}'
    found = list(re.finditer(pattern, source, re.M | re.S))
    if len(found) != 1:
        raise ValueError('exact resource function drift: ' + name)
    return found[0]


def enter(source, name, code):
    match = function(source, name)
    pos = match[0].index('{\n') + 2
    body = match[0][:pos] + GUARD + code + '#endif\n' + match[0][pos:]
    return source[:match.start()] + body + source[match.end():]


def clock_names(source, table):
    match = re.search(r'static struct \w+ ' + table + r'\[\] = \{(.*?)\n\};', source, re.S)
    if not match:
        raise ValueError('actual vendor clock table drift: ' + table)
    return re.findall(r'"([\w-]+)"', match[1])


def kernel_contract(archive):
    expected = '5d809b44f94336549285a559909bfe5d8b2dcc3f213af58c25a52d535cd2cd0345ce34f44e1d155940cf0d4089fd2ad49fa0d6829fd2b965095084cd1500003c'
    digest = hashlib.sha512()
    with archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError('not the pinned Linux source archive')
    names = ('drivers/base/platform.c', 'drivers/base/dd.c', 'drivers/of/platform.c',
             'drivers/of/irq.c', 'drivers/of/base.c', 'include/linux/platform_device.h')
    with tarfile.open(archive) as tar:
        sources = {name: tar.extractfile('linux-' + LINUX + '/' + name).read() for name in names}
    platform = sources[names[0]].decode()
    body = function(platform, 'platform_probe')[0]
    if not body.index('dev_pm_domain_attach(') < body.index('drv->probe(dev)'):
        raise ValueError('Linux PM attachment order drift')
    if 'PD_FLAG_ATTACH_POWER_ON' not in body or 'of_clk_set_defaults(' not in body:
        raise ValueError('Linux pre-probe PM/clock behavior drift')
    if 'void (*remove)(struct platform_device *);' not in sources[names[-1]].decode():
        raise ValueError('Linux platform remove ABI drift')
    return {'source_sha256': {name: sha(data) for name, data in sources.items()},
            'archive_sha512': expected, 'r181_dt': baseline_dt(archive)}


def baseline_dt(archive):
    """Reconstruct the actual r181 DT sources; no cpp/dtc/build is executed."""
    package = 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878/'
    def committed(name):
        return subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                        BASELINE + ':' + package + name]).decode('latin-1')
    apk = committed('APKBUILD')
    block = re.search(r'^source="\n(.*?)^"$', apk, re.M | re.S)
    if not block or '_commit="' + LINUX + '"' not in apk:
        raise ValueError('r181 package DT pin drift')
    patches = [name for name in block[1].split() if name.endswith('.patch')]
    prefix = 'arch/arm64/boot/dts/mediatek/'
    applied, diagnostics = {}, {}
    with tempfile.TemporaryDirectory(prefix='tetris-r181-dt-') as temp:
        root = Path(temp)
        with tarfile.open(archive) as tar:
            for member in tar:
                rel = member.name.removeprefix('linux-' + LINUX + '/')
                if rel.startswith(prefix) and member.isfile() and rel.endswith(('.dts', '.dtsi', '.h')):
                    target = root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
        for name in patches:
            patch = committed(name)
            # Historical package files contain both git and plain unified
            # sections, including orig/new paths and timestamped headers.
            headers = list(re.finditer(r'^--- [^\n]+\n\+\+\+ (\S+)[^\n]*\n', patch, re.M))
            selected = []
            for index, match in enumerate(headers):
                target = match[1].split('/', 1)[-1]
                if not target.startswith(prefix) or not target.endswith(('.dts', '.dtsi', '.h')):
                    continue
                end = headers[index + 1].start() if index + 1 < len(headers) else len(patch)
                section = patch[match.start():end].split('\ndiff ')[0].split('\n-- \n')[0]
                selected.append(section + '\n')
            selected = ''.join(selected)
            if not selected:
                continue
            checked = subprocess.run(['patch', '--batch', '--forward', '-p1'], cwd=root, input=selected,
                                     text=True, encoding='latin-1', capture_output=True)
            if checked.returncode:
                raise ValueError('r181 DT patch application failed: ' + name + '\n' + checked.stdout + checked.stderr)
            if 'offset' in checked.stdout or 'fuzz' in checked.stdout:
                diagnostics[name] = checked.stdout
            applied[name] = sha(patch.encode('latin-1'))
        visited = {}
        def visit(name):
            path = root / prefix / name
            if name in visited:
                return
            source = path.read_text()
            visited[name] = source
            for include in re.findall(r'^#include "([^\"]+)"', source, re.M):
                visit(include)
        visit('mt6878-nothing-tetris.dts')
        visit('mt6878-nothing-tetris-native.dts')
        combined = '\n'.join(visited.values())
        anchor = re.findall(r'mddriver:\s*modem\s*\{(.*?)\n\s*\};', combined, re.S)
        if len(anchor) != 1 or 'status = "disabled";' not in anchor[0]:
            raise ValueError('r181 disabled metadata anchor drift')
        for token in ('reg =', 'interrupts =', 'power-domains =', 'clocks ='):
            if token in anchor[0]:
                raise ValueError('r181 metadata anchor acquired physical resources')
        presence = {module: sum(source.count('"' + row[3] + '"') for source in visited.values())
                    for module, row in CENSUS.items() if row[3]}
        if presence != {module: int(module == 'ccci_md_all') for module in presence}:
            raise ValueError('additional automatic modem DT target in r181 source closure')
        return {'dtb_sources': ['mt6878-nothing-tetris.dts', 'mt6878-nothing-tetris-native.dts'],
                'include_source_sha256': {name: sha(source.encode()) for name, source in sorted(visited.items())},
                'applied_dt_patch_sha256': applied, 'compatible_occurrences': presence,
                'historical_dt_patch_policy': 'r181 default_prepare patch policy; not the exact-context new resource overlay',
                'historical_dt_patch_diagnostics': diagnostics,
                'mddriver_body': anchor[0],
                'scope': 'source closure only; parent must census the actual boot FDT/platform devices'}


def build(vendor):
    link = load('resources_full_stack', HERE.parent / 'runtime-link-closure/link_full.py')
    consumer = load('resources_smem_stack', HERE.parent / 'runtime-smem-consumer/check_consumer.py')
    report = {}
    with tempfile.TemporaryDirectory(prefix='tetris-hif-source-') as temp:
        stage = Path(temp) / 'vendor'
        link.stage(vendor, stage, report)
        targets = {'fsm/md_sys1_platform.c', 'fsm/register_prepare.h',
                   'fsm/ccci_tetris_dependencies.h', 'hif/ccci_hif_ccif.c',
                   'hif/ccci_dpmaif_com.c', 'hif/ccci_hif_cldma.c',
                   'ccci_auxadc.c', 'fsm/ccci_fsm_scp_c.c'}
        before = {ECCCI + name: (stage / ECCCI / name).read_text() for name in targets}
        v3 = (stage / ECCCI / 'hif/ccci_dpmaif_drv_v3.c').read_text()
        vendor_dt = subprocess.check_output(['git', '-C', str(vendor), 'show',
            VENDOR + ':arch/arm64/boot/dts/mediatek/mt6878.dts'], text=True)
        vendor_nodes = {}
        for label in ('ccifdriver', 'dpmaif', 'mddriver'):
            found = re.findall(r'\b' + label + r'\s*:\s*[^\n{]+\{(.*?)\n\s*\};', vendor_dt, re.S)
            if len(found) != 1:
                raise ValueError('B4.1 modem/HIF DT node drift: ' + label)
            vendor_nodes[label] = found[0]
        if 'ccif-pericfg' in vendor_nodes['ccifdriver'] or 'power-domains' not in vendor_nodes['mddriver']:
            raise ValueError('B4.1 pericfg/PM gate source drift')
        ccif_source = before[ECCCI + 'hif/ccci_hif_ccif.c']
        reset = function(ccif_source, 'ccif_set_clk_off')
        lookup = function(ccif_source, 'ccif_hif_hw_init')
        reset_body = re.sub(r'\s+', '', reset[0])
        if ('ccif_ctrl->plat_val.md_gen>=6298' not in reset_body or
                'elseif(ccif_ctrl->plat_val.md_gen<=6297)' not in reset_body or
                reset_body.count('regmap_write(ccif_ctrl->pericfg_base,0x30c,0x0);') != 1 or
                'mediatek,md-generation = <6299>;' not in vendor_nodes['mddriver']):
            raise ValueError('B4.1 pericfg generation contract drift')
        outside = ccif_source
        for match in sorted((reset, lookup), key=lambda item: item.start(), reverse=True):
            outside = outside[:match.start()] + outside[match.end():]
        if 'pericfg_base' in outside:
            raise ValueError('new CCIF pericfg user outside the reviewed generation path')
        pericfg = dict(policy='optional for resource-only MT6878/6299; validate if present',
                       reset_body_sha256=sha(reset[0].encode()),
                       lookup_body_sha256=sha(lookup[0].encode()), generation=6299)
        old_census = census(stage)
        after = dict(before)
        for local, target in PAYLOADS.items():
            after[ECCCI + target] = (HERE / local).read_text()
        ccif = ECCCI + 'hif/ccci_hif_ccif.c'
        dpmaif = ECCCI + 'hif/ccci_dpmaif_com.c'
        for path, table, actual, id_name, probe, driver, init, exit_name, compatible, new_name in (
            (ccif, 'ccif_clk_table', before[ccif], 'CCIF_HIF_ID', 'ccci_hif_ccif_probe',
             'ccci_hif_ccif_driver', 'ccci_hif_ccif_init', 'ccci_hif_ccif_exit', 'mediatek,ccci_ccif', 'tetris_ccif_resources'),
            (dpmaif, 'g_clk_tbs', v3, 'DPMAIF_HIF_ID', 'dpmaif_probe',
             'g_dpmaif_driver', 'ccci_dpmaif_init', 'ccci_dpmaif_exit', 'mediatek,dpmaif', 'tetris_dpmaif_resources')):
            clocks = clock_names(actual, table)
            if len(clocks) != (6 if id_name == 'CCIF_HIF_ID' else 3):
                raise ValueError('clock capacity drift')
            declaration = GUARD + '#include "tetris_hif_supplier.h"\n' + \
                'static const char *const tetris_hif_clocks[] = {\n' + \
                ''.join('\t"' + name + '",\n' for name in clocks) + '};\n#endif\n\n'
            match = function(after[path], probe)
            after[path] = after[path][:match.start()] + declaration + after[path][match.start():]
            if id_name == 'CCIF_HIF_ID':
                code = '\treturn tetris_hif_supplier_probe(pdev, CCIF_HIF_ID,\n\t\ttetris_hif_clocks, ARRAY_SIZE(tetris_hif_clocks), 2);\n'
                after[path] = enter(after[path], 'ccci_ccif_hif_init', '\treturn -EOPNOTSUPP;\n')
            else:
                code = ('\tu32 version, platform, capability;\n\tint error;\n'
                        '\terror = of_property_read_u32(pdev->dev.of_node, "mediatek,dpmaif-ver", &version);\n'
                        '\tif (error)\n\t\treturn error;\n'
                        '\terror = of_property_read_u32(pdev->dev.of_node, "mediatek,plat-info", &platform);\n'
                        '\tif (error)\n\t\treturn error;\n'
                        '\terror = of_property_read_u32(pdev->dev.of_node, "mediatek,dpmaif-cap", &capability);\n'
                        '\tif (error)\n\t\treturn error;\n'
                        '\tif (version != 3 || platform != 6878)\n\t\treturn -EOPNOTSUPP;\n'
                        '\treturn tetris_hif_supplier_probe(pdev, DPMAIF_HIF_ID,\n'
                        '\t\ttetris_hif_clocks, ARRAY_SIZE(tetris_hif_clocks),\n'
                        '\t\tcapability & (DPMAIF_CAP_LRO | DPMAIF_CAP_2RXQ) ? DPMAIF_RXQ_NUM : 1);\n')
                after[path] = enter(after[path], 'dpmaif_init_com', '\treturn -EOPNOTSUPP;\n')
            after[path] = enter(after[path], probe, code)
            old_name = 'ccci_hif_ccif' if id_name == 'CCIF_HIF_ID' else 'ccci_dpmaif_driver'
            after[path] = replace(after[path], '\t\t.name = "' + old_name + '",',
                GUARD + '\t\t.name = "' + new_name + '",\n#else\n\t\t.name = "' + old_name + '",\n#endif')
            pm = 'ccif_pm_ops' if id_name == 'CCIF_HIF_ID' else 'g_dpmaif_pm_ops'
            after[path] = replace(after[path], '\t\t.pm = &' + pm + ',',
                GUARD + '\t\t.pm = NULL,\n#else\n\t\t.pm = &' + pm + ',\n#endif')
            after[path] = replace(after[path], '\t.probe = ' + probe + ',',
                '\t.probe = ' + probe + ',\n' + GUARD + '\t.remove = tetris_hif_supplier_remove,\n#endif')
            after[path] = replace(after[path], '\tret = platform_driver_register(&' + driver + ');',
                GUARD + '\tret = tetris_preflight_driver("' + compatible + '");\n'
                '\tif (ret)\n\t\treturn ret;\n#endif\n\tret = platform_driver_register(&' + driver + ');')
            after[path] = enter(after[path], exit_name, '\tplatform_driver_unregister(&' + driver + ');\n')
        dep = ECCCI + 'fsm/ccci_tetris_dependencies.h'
        after[dep] = GUARD + '#include "tetris_hif_consumer.h"\n#endif\n' + after[dep]
        after[dep] = enter(after[dep], 'tetris_ccci_dependencies', '\treturn tetris_resource_dependencies(consumer);\n')
        registration = ECCCI + 'fsm/register_prepare.h'
        # Actual early leases replace slot-based module pins, with no new export cycle.
        match = function(after[registration], 'tetris_pin_hif_modules')
        after[registration] = after[registration][:match.start()] + \
            '#if !IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n' + match[0] + \
            '\n#endif' + after[registration][match.end():]
        after[registration] = replace(after[registration],
            'static struct module *tetris_registration_hif_modules[2];',
            '#if !IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n'
            'static struct module *tetris_registration_hif_modules[2];\n#endif')
        after[registration] = replace(after[registration],
            '\tret = tetris_pin_hif_modules();\n\tif (ret)\n\t\tgoto abort_ports;',
            '#if !IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n'
            '\tret = tetris_pin_hif_modules();\n\tif (ret)\n\t\tgoto abort_ports;\n#endif')
        after[registration] = replace(after[registration],
            '\tpdev->dev.dma_mask = &mddriver_dmamask;\n\tpdev->dev.coherent_dma_mask = mddriver_dmamask;',
            '#if !IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n'
            '\tpdev->dev.dma_mask = &mddriver_dmamask;\n\tpdev->dev.coherent_dma_mask = mddriver_dmamask;\n#endif')
        platform = ECCCI + 'fsm/md_sys1_platform.c'
        anchor = 'static int md_cd_get_modem_hw_info('
        after[platform] = replace(after[platform], anchor,
            GUARD + '#include "tetris_modem_resources.h"\n'
            'static bool tetris_private_prepare;\n'
            'module_param_named(private_prepare, tetris_private_prepare, bool, 0400);\n'
            'MODULE_PARM_DESC(private_prepare, "Opt in to checked private preparation; no hardware activation");\n'
            '#endif\n\n' + anchor)
        after[platform] = enter(after[platform], 'md_cd_get_modem_hw_info',
            '\treturn tetris_modem_hw_resources(dev_ptr, dev_cfg, hw_info);\n')
        after[platform] = enter(after[platform], 'ccci_modem_probe',
            '\tif (!tetris_private_prepare)\n\t\treturn -EOPNOTSUPP;\n')
        after[platform] = replace(after[platform], '\tret = platform_driver_register(&ccci_modem_driver);',
            GUARD + '\t/* Loading the full core does not request private preparation. */\n'
            '\tif (!tetris_private_prepare)\n\t\treturn 0;\n'
            '\tret = tetris_preflight_driver("mediatek,mddriver");\n'
            '\tif (ret)\n\t\treturn ret;\n#endif\n'
            '\tret = platform_driver_register(&ccci_modem_driver);')
        after[platform] = enter(after[platform], 'modem_cd_exit',
            '\tif (tetris_private_prepare)\n\t\tplatform_driver_unregister(&ccci_modem_driver);\n')
        # Optional companions retain exports but cannot initialize physical paths.
        for suffix, probe, init in (('hif/ccci_hif_cldma.c', 'ccci_hif_cldma_probe', 'ccci_cldma_init'),
                                    ('ccci_auxadc.c', 'get_auxadc_probe', 'ccci_auxadc_init'),
                                    ('fsm/ccci_fsm_scp_c.c', 'ccci_scp_probe', 'ccci_scp_init')):
            path = ECCCI + suffix
            after[path] = enter(after[path], probe, '\treturn -EOPNOTSUPP;\n')
            after[path] = enter(after[path], init,
                '\t/* Export-only companion; do not register a physical driver. */\n\treturn 0;\n')
        patch = consumer.patch(before, after)
        consumer.apply_check(patch, before)
        # Full source census is taken both before and after this additive overlay.
        subprocess.run(['git', 'apply', '--check', '-'], cwd=stage, input=patch,
                       text=True, check=True, capture_output=True)
        subprocess.run(['git', 'apply', '-'], cwd=stage, input=patch,
                       text=True, check=True, capture_output=True)
        for path, source in after.items():
            if (stage / path).read_text() != source:
                raise ValueError('whole-tree application differs from generator: ' + path)
        new_census = census(stage)
    report = {key: report[key] for key in ('frozen_reviews', 'overlays_sha256',
              'consumer_review_sha256', 'package_sha256', 'vendor_prepare')}
    report.update(vendor_commit=VENDOR, linux_commit=LINUX, baseline_commit=BASELINE,
                  ccif_pericfg=pericfg,
                  overlay_sha256=sha(patch.encode()),
                  base_init_census=old_census, resource_init_census=new_census,
                  touched_source_sha256={name: sha(source.encode()) for name, source in sorted(after.items())},
                  dpmaif_clock_source_sha256=sha(v3.encode()),
                  vendor_dt={'source': 'arch/arm64/boot/dts/mediatek/mt6878.dts',
                             'source_sha256': sha(vendor_dt.encode()), 'nodes': vendor_nodes},
                  status='source-only; native and ARM64/link pending; no hardware operations')
    return patch, before, after, report


def census(stage):
    result = {}
    for module, (path, init, probe, compatible) in CENSUS.items():
        source = (stage / PREFIX / path).read_text()
        row = {'source': PREFIX + path, 'source_sha256': sha(source.encode()),
               'module_init': init, 'probe': probe, 'compatible': compatible}
        if init:
            if source.count('module_init(' + init + ');') != 1:
                raise ValueError('module init drift: ' + module)
            row['init_body'] = function(source, init)[0]
            row['probe_body'] = function(source, probe)[0]
            if module == 'ccci_fsm_scp':
                common = (stage / ECCCI / 'ccci_common_config.h').read_text()
                if '#if IS_ENABLED(CONFIG_MTK_TINYSYS_SCP_SUPPORT)\n#define FEATURE_SCP_CCCI_SUPPORT\n#endif' not in common:
                    raise ValueError('actual SCP module-init feature guard drift')
                row['feature_input_source_sha256'] = sha(common.encode())
                row['feature_guard'] = 'IS_ENABLED(CONFIG_MTK_TINYSYS_SCP_SUPPORT) -> FEATURE_SCP_CCCI_SUPPORT'
            # No matching platform probe: the automatic init body must only
            # register a driver/log/check the explicit preparation request.
            for token in ('of_iomap(', 'ioremap', 'request_irq(', 'dma_alloc', 'arm_smccc', 'of_find_compatible_node('):
                if token in row['init_body']:
                    raise ValueError('new automatic physical/OF init: ' + module + ':' + token)
        else:
            if re.search(r'\b(?:module_init|\w+_initcall)\s*\(', source):
                raise ValueError('unexpected module constructor: ' + module)
        result[module] = row
    # Retain all global searches, including those in non-init/runtime helpers;
    # status is not inferred from lookup alone. This is a lexical census, not
    # a fabricated call graph or a claim that every compiled branch is active.
    searches = {}
    for directory in ('eccci', 'ccmni', 'rps'):
        for path in sorted((stage / PREFIX / directory).rglob('*.c')):
            rows = [{'line': index, 'source': line.strip()} for index, line in
                    enumerate(path.read_text().splitlines(), 1)
                    if 'of_find_compatible_node(' in line]
            if rows:
                searches[str(path.relative_to(stage))] = rows
    result['global_of_searches'] = searches
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--linux-archive', type=Path)
    parser.add_argument('--print-generated', action='store_true')
    args = parser.parse_args()
    kernel = kernel_contract(args.linux_archive) if args.linux_archive else None
    patch, _, _, report = build(args.vendor.resolve())
    if kernel:
        report['linux_contract'] = kernel
    if args.print_generated:
        print(json.dumps({'resources.overlay': patch,
                          'SOURCE-EVIDENCE.json': json.dumps(report, indent=2) + '\n'}))
        return
    review()
    if patch != (HERE / 'resources.overlay').read_text():
        raise ValueError('reviewed resource overlay differs from exact generator output')
    frozen = json.loads((HERE / 'SOURCE-EVIDENCE.json').read_text())
    for key, value in report.items():
        if frozen.get(key) != value:
            raise ValueError('reviewed source evidence drift: ' + key)
    print('Exact complete-stack resource overlay generation/application PASS; no compilation or activation')


def review():
    rows = {}
    for line in (HERE / 'REVIEW.sha256').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in rows or sha((HERE / match[2]).read_bytes()) != match[1]:
            raise ValueError('resource review manifest drift: ' + line)
        rows[match[2]] = match[1]
    expected = {path.name for path in HERE.iterdir() if path.is_file() and path.name != 'REVIEW.sha256'}
    if set(rows) != expected:
        raise ValueError('resource review manifest coverage differs')


if __name__ == '__main__':
    main()
