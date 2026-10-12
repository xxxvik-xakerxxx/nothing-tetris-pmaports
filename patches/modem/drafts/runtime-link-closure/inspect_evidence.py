#!/usr/bin/env python3
"""Read genuine r181 ELF/export evidence without compiling or executing modules.

Requires pyelftools. This is an optional offline check, not a build dependency.
"""
import argparse
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
from link_full import BASELINE, BACKEND_EXPORTS, CONFIG_SHA, EXPORTS_SHA, sha, symvers


def inspect(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['source_commit'] != BASELINE:
        raise ValueError('wrong baseline')
    if sha(root / '.config') != CONFIG_SHA or sha(root / 'Module.symvers') != EXPORTS_SHA:
        raise ValueError('not the genuine pinned r181 config/exports')
    names = ['modem-link/Module.symvers', 'modem-metadata/Module.symvers']
    names += sorted(name for name in manifest['sha256'] if name.startswith('modem-link/') and name.endswith('.ko'))
    for name in names:
        if sha(root / name) != manifest['sha256'][name]:
            raise ValueError('evidence member hash mismatch: ' + name)
    kernel = symvers(root / 'Module.symvers')
    vendor = symvers(root / 'modem-link/Module.symvers')
    metadata = symvers(root / 'modem-metadata/Module.symvers')
    legacy = {name for name, row in vendor.items() if Path(row[2]).name == 'ccci_util_lib'}
    report = {'baseline_commit': BASELINE,
              'kernel_symvers_sha256': EXPORTS_SHA,
              'first_start_exports_missing_from_r181': sorted(set(BACKEND_EXPORTS) - kernel.keys()),
              'legacy_util_exports_missing_from_ap_only_provider': sorted(legacy - metadata.keys()),
              'modules': {}}
    for name in names:
        if not name.endswith('.ko'):
            continue
        with (root / name).open('rb') as stream:
            elf = ELFFile(stream)
            if elf['e_machine'] != 'EM_AARCH64':
                raise ValueError('wrong architecture: ' + name)
            imports = {symbol.name for symbol in elf.get_section_by_name('.symtab').iter_symbols()
                       if symbol['st_shndx'] == 'SHN_UNDEF' and symbol.name}
            info = elf.get_section_by_name('.modinfo').data().decode().split('\0')
            providers = {symbol: [table[symbol][2] for table in (kernel, vendor) if symbol in table]
                         for symbol in sorted(imports)}
            if any(len(matches) != 1 for matches in providers.values()):
                raise ValueError('unresolved/duplicate baseline import: ' + name)
            report['modules'][name] = {
                'depends': next(item.removeprefix('depends=') for item in info if item.startswith('depends=')),
                'non_vmlinux_imports': {symbol: owners[0] for symbol, owners in providers.items()
                                       if owners != ['vmlinux']}}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    print(json.dumps(inspect(parser.parse_args().evidence), indent=2))
