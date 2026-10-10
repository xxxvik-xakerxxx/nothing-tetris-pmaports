#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Refusing native compilation outside CI.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/gpueb-mfg0.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
"${HOSTCC:-cc}" -std=gnu11 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/native-test.c" -o "$work/test"
"$work/test"
