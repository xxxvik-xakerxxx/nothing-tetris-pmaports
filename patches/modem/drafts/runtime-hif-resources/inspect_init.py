#!/usr/bin/env python3
"""Read actual full-link artifact constructor identities; never load modules."""
import argparse
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
from check_resources import HERE, CENSUS, VENDOR, LINUX, BASELINE, sha

CONFIG_SHA = 'edcbdf45d3201aef8ab71157bb485c074bc5c3457f564f0341a7eb410b9382a2'
EXPORTS_SHA = '2e58e05288219f07094e88da49b9f12b1c06d2bf5875e87e1f557bc36c4e7cf3'


def inspect(root, profile):
    report = json.loads((root / 'full-link.json').read_text())
    expected = {'vendor_commit': VENDOR, 'linux_commit': LINUX, 'baseline_commit': BASELINE,
                'config_sha256': CONFIG_SHA, 'kernel_symvers_sha256': EXPORTS_SHA, 'status': 'passed'}
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError('actual full-link input mismatch: ' + key)
    flags = ' '.join(report['command'])
    for flag in ('-DCONFIG_MTK_ECCCI_TETRIS_OWNER=1', '-DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1'):
        if flag not in flags:
            raise ValueError('missing actual consumer build flag: ' + flag)
    resource_flag = '-DCONFIG_TETRIS_CCCI_HIF_RESOURCES=1'
    if (resource_flag in flags) != (profile == 'resource'):
        raise ValueError('wrong optional artifact profile')
    if '-DCONFIG_MTK_TINYSYS_SCP_SUPPORT' in flags:
        raise ValueError('SCP feature override differs from the reviewed actual r181 profile')
    evidence = json.loads((HERE / 'SOURCE-EVIDENCE.json').read_text())
    if profile == 'resource':
        recorded = report.get('hif_resources', {})
        if (recorded.get('overlay_sha256') != evidence['overlay_sha256'] or
                recorded.get('overlay_sha256') != sha((HERE / 'resources.overlay').read_bytes())):
            raise ValueError('resource artifact belongs to a different reviewed overlay')
        for name, digest in evidence['touched_source_sha256'].items():
            if report['vendor_source_sha256'].get(name) != digest:
                raise ValueError('compiled resource header/source differs: ' + name)
    census = evidence['resource_init_census' if profile == 'resource' else 'base_init_census']
    module_rows = report['modules']
    if {Path(name).name for name in module_rows} != set(CENSUS):
        raise ValueError('not the actual eight-module full-link result')
    result = {'profile': profile, 'full_link_report_sha256': sha((root / 'full-link.json').read_bytes()),
              'scope': 'verified ELF constructors and matched production sources; no load or instruction execution',
              'modules': {}}
    for name, identity in module_rows.items():
        module = Path(name).name
        source = census[module]['source']
        if report['vendor_source_sha256'].get(source) != census[module]['source_sha256']:
            raise ValueError('compiled source differs from reviewed census: ' + source)
        path = root / 'artifacts' / (name + '.ko')
        if sha(path.read_bytes()) != identity['sha256']:
            raise ValueError('actual module member hash mismatch: ' + name)
        with path.open('rb') as stream:
            elf = ELFFile(stream)
            if elf['e_machine'] != 'EM_AARCH64':
                raise ValueError('not an AArch64 module: ' + name)
            symbols = list(elf.get_section_by_name('.symtab').iter_symbols())
            constructors = [s for s in symbols if s.name == 'init_module' and s['st_shndx'] != 'SHN_UNDEF']
            if len(constructors) > 1:
                raise ValueError('ambiguous actual constructor: ' + name)
            aliases = []
            if constructors:
                init = constructors[0]
                aliases = [s.name for s in symbols if s['st_value'] == init['st_value'] and
                           s['st_shndx'] == init['st_shndx'] and s['st_info']['type'] == 'STT_FUNC']
            # The selected SCP feature is absent in genuine r181 generated config.
            expected_init = module not in ('ccmni', 'rps_perf', 'ccci_fsm_scp')
            if bool(constructors) != expected_init:
                raise ValueError('actual r181 constructor/feature census mismatch: ' + name)
            info = elf.get_section_by_name('.modinfo').data().decode().split('\0')
            if profile == 'resource' and module == 'ccci_md_all' and not any(
                    entry == 'parmtype=private_prepare:bool' for entry in info):
                raise ValueError('actual separate private_prepare request parameter absent')
            result['modules'][module] = {'sha256': identity['sha256'],
                'has_constructor': bool(constructors), 'constructor_aliases': aliases,
                'reviewed_declared_init': census[module]['module_init'],
                'source_sha256': census[module]['source_sha256']}
    result['next_gate'] = 'parent must review constructor instructions/profile and actual boot FDT/platform devices before load; no hardware permission inferred'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('full_link_root', type=Path)
    parser.add_argument('--profile', choices=('base', 'resource'), required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.full_link_root, args.profile), indent=2))
