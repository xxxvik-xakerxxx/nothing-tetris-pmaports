#!/usr/bin/env python3
"""Validate the disabled metadata consumer in the compiled shipping DTB."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/modem'))
from check_preflight_dt import compatible, read_tree, require

EXPECTED = {
    'compatible': b'mediatek,mddriver\0',
    'mediatek,ap-plat-info': (6878).to_bytes(4, 'big'),
    'mediatek,md-generation': (6299).to_bytes(4, 'big'),
    'status': b'disabled\0',
}


def validate(tree):
    consumers = [path for path, props in tree.items()
                 if b'mediatek,mddriver' in compatible(props)]
    require(consumers == ['/modem'], 'Expected exactly one root metadata consumer')
    actual = {name: value for name, value in tree['/modem'].items()
              if name not in ('phandle', 'linux,phandle')}
    require(actual == EXPECTED, 'CCCI metadata consumer changed or gained physical resources')
    require(not any(path.startswith('/modem/') for path in tree), 'Unexpected modem child')
    require('/reserved-memory/tetris-modem-linux-tags' not in tree,
            'Shipping DT must not inherit an owned AP tag reservation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dtb', type=Path)
    args = parser.parse_args()
    validate(read_tree(args.dtb))
    print('PASS: sole disabled CCCI metadata consumer; no inherited tags or physical resources')
