#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pmb="$repo_root/upstream/pmbootstrap/pmbootstrap.py"

if [ ! -x "$pmb" ]; then
	echo "pmbootstrap.py not found at $pmb" >&2
	exit 1
fi

cd "$repo_root/upstream/pmbootstrap"

./pmbootstrap.py init
./pmbootstrap.py checksum device-nothing-tetris linux-postmarketos-mediatek-mt6878
./pmbootstrap.py build device-nothing-tetris
./pmbootstrap.py build linux-postmarketos-mediatek-mt6878
./pmbootstrap.py install --android-recovery-zip

