#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read staged loader observations from Linux /chosen; never hardware access."""
import argparse
import json
from pathlib import Path

PREFIX = 'nothing,gpueb-initial-'
HEADER = ('report-version', 'report-stage', 'report-error')
DATA = ('spm-raw', 'spm-ack', 'spm-pdn-ack12', 'spm-sleep-b-ack13')


def read_report(chosen):
    def read(name):
        with (chosen / (PREFIX + name)).open('rb') as stream:
            value = stream.read(5)
        if len(value) != 4:
            raise ValueError('expected one big-endian u32: ' + name)
        return int.from_bytes(value, 'big')

    fields = {name: read(name) for name in HEADER}
    if fields['report-version'] != 1 or fields['report-stage'] not in (0, 1):
        raise ValueError('unknown report version/stage; not an initial-state observation')
    stage = fields['report-stage']
    error = fields['report-error']
    if error & 0x80000000:
        error -= 1 << 32
    if (stage == 0 and error == 0) or (stage == 1 and error != 0):
        raise ValueError('inconsistent capture stage/error')
    result = {'stage': stage, 'error': error,
              'meaning': 'loader diagnostic, not authenticated power ownership or GPU readiness',
              'producer': 'SPM/preloader/EL3 MFG0 state producer unresolved'}
    if stage == 0:
        if any((chosen / (PREFIX + name)).exists() for name in DATA):
            raise ValueError('error report contains stale/raw sample fields')
        return result
    fields.update({name: read(name) for name in DATA})
    raw = fields['spm-raw']
    if (fields['spm-ack'], fields['spm-pdn-ack12'], fields['spm-sleep-b-ack13']) != \
            ((raw >> 30) & 3, (raw >> 12) & 1, (raw >> 13) & 1):
        raise ValueError('reported ACK fields disagree with the same raw sample')
    result.update(phase='startup-post-relocation-before-main-loop', raw=f'{raw:08x}',
                  ack=(raw >> 30) & 3, pdn_ack12=(raw >> 12) & 1, sleep_b_ack13=(raw >> 13) & 1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chosen', type=Path, required=True,
                        help='Linux /sys/firmware/devicetree/base/chosen or a static fixture')
    args = parser.parse_args()
    try:
        result = read_report(args.chosen)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    if result['error']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
