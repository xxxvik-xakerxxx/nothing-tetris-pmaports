#!/bin/sh
# CI-only native compilation; the backend has no live MMIO adapter.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer "$here/mux-test.c" -o "$tmp/mux-test"
"$tmp/mux-test"
