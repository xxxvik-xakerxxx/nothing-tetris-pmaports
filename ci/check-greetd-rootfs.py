#!/usr/bin/env python3
"""Read-only pre-tmpfiles ownership and effective-access gate."""
import os
from pathlib import Path
import stat
import sys

HOME = '/var/lib/greetd'
DCONF = HOME + '/.config/dconf'


def identity(passwd, group):
    users = [line.split(':') for line in passwd.splitlines() if line.startswith('greetd:')]
    groups = [line.split(':') for line in group.splitlines() if line.startswith('greetd:')]
    if len(users) != 1 or len(users[0]) != 7 or len(groups) != 1 or len(groups[0]) != 4:
        raise ValueError('expected exactly one valid greetd passwd/group entry')
    user, entry = users[0], groups[0]
    if not all(value.isascii() and value.isdecimal() for value in (user[2], user[3], entry[2])):
        raise ValueError('greetd UID/GID must be numeric')
    uid, gid = int(user[2]), int(user[3])
    if uid == 0 or gid == 0 or gid != int(entry[2]) or user[5] != HOME:
        raise ValueError(f'invalid greetd identity/home: {uid}:{gid}:{user[5]}')
    return uid, gid


def check_metadata(root, uid, gid):
    for path in ('/var', '/var/lib', HOME, HOME + '/.config', DCONF):
        info = (root / path.lstrip('/')).lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f'{path}: expected real directory, not symlink')
        mode = stat.S_IMODE(info.st_mode)
        if path == DCONF:
            if info.st_uid != uid or mode != 0o700:
                raise ValueError(f'{path}: actual {mode:o}:{info.st_uid}:{info.st_gid}; '
                                 f'expected 700 owner UID {uid}; do not rely on tmpfiles repair')
        else:
            bit = 0o100 if info.st_uid == uid else 0o010 if info.st_gid == gid else 0o001
            if not mode & bit:
                raise ValueError(f'{path}: {mode:o}:{info.st_uid}:{info.st_gid} '
                                 f'not searchable by {uid}:{gid}')


def check_access(root, uid, gid):
    # Drop real/effective IDs in a child before access(2); execute no target code.
    pid = os.fork()
    if pid == 0:
        try:
            os.chroot(root)
            os.chdir('/')
            os.setgroups([gid])
            os.setgid(gid)
            os.setuid(uid)
            os._exit(0 if os.access(DCONF, os.W_OK | os.X_OK) else 1)
        except OSError as error:
            os.write(2, f'greetd access probe: {error}\n'.encode())
            os._exit(2)
    _, status = os.waitpid(pid, 0)
    if status != 0:
        raise ValueError(f'effective greetd access probe failed (wait status {status})')


def check(root):
    uid, gid = identity((root / 'etc/passwd').read_text(), (root / 'etc/group').read_text())
    check_metadata(root, uid, gid)
    check_access(root, uid, gid)
    print(f'PASS: pre-tmpfiles dconf owner/write/search access for greetd {uid}:{gid}; '
          'directory GID is immaterial at mode 0700')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or os.geteuid() != 0:
            raise ValueError('usage (as root): check-greetd-rootfs.py ROOTFS')
        check(Path(sys.argv[1]).resolve(strict=True))
    except (ValueError, OSError) as error:
        sys.exit(f'FAIL: greetd rootfs: {error}')
