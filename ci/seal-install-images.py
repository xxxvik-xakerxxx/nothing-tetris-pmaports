#!/usr/bin/env python3
"""Check detached pmbootstrap images before exporting flash artifacts."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess


def image_path(value):
    path = Path(value)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
        raise ValueError(f'expected nonempty regular image, not device/symlink: {path}')
    return path.resolve(strict=True)


def check_detached(images, inventory):
    loops = inventory.get('loopdevices')
    if not isinstance(loops, list):
        raise ValueError('missing loop-device inventory')
    for loop in loops:
        backing = loop.get('back-file')
        if not isinstance(backing, str) or not backing:
            raise ValueError('cannot establish loop backing-file identity')
        path = Path(backing.removesuffix(' (deleted)'))
        if not path.is_absolute():
            raise ValueError('loop backing-file path is not absolute')
        for image in images:
            if path.resolve() == image or (path.exists() and path.samefile(image)):
                raise ValueError(f'image still attached to {loop.get("name")}: {image}')


def command(argv, allowed=(0,)):
    result = subprocess.run(argv, env={**os.environ, 'LC_ALL': 'C'}, check=False)
    if result.returncode not in allowed:
        raise ValueError(f'{argv[0]} failed with status {result.returncode}')
    return result.returncode


def seal(images):
    images = [image_path(value) for value in images]
    if len({(p.stat().st_dev, p.stat().st_ino) for p in images}) != len(images):
        raise ValueError('duplicate image identity')
    results = []
    for image in images:
        # A loop association remains unsafe even when its mount was removed.
        inventory = subprocess.check_output(
            ['losetup', '--json', '--list', '--output', 'NAME,BACK-FILE'], text=True)
        check_detached(images, json.loads(inventory))
        size = image.stat().st_size
        command(['dumpe2fs', '-h', str(image)])
        repaired = command(['e2fsck', '-f', '-p', str(image)], allowed=(0, 1))
        command(['e2fsck', '-f', '-n', str(image)])
        # With no size argument a raw image must already occupy its full extent.
        # This also exercises resize2fs's last-check/last-mount safety gate.
        command(['resize2fs', str(image)])
        if image.stat().st_size != size:
            raise ValueError(f'filesystem/image extent mismatch: {image}')
        command(['e2fsck', '-f', '-n', str(image)])
        results.append({'image': image.name, 'bytes': size,
                        'fsck_status': repaired, 'resize_ready': True})
    print(json.dumps({'images': results}, sort_keys=True))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    args = parser.parse_args()
    try:
        seal(args.images)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f'FAIL: image sealing: {error}\n')
