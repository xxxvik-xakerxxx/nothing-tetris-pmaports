#!/bin/sh
# CI-only native compilation; never execute against live MMIO.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer "$here/phy-test.c" -o "$tmp/phy-test"
"$tmp/phy-test"
