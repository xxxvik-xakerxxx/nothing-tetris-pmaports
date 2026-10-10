#!/bin/sh
# CI-only in-memory register fixture, never live hardware.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I"$here/../camera-seninf" \
    "$here/route-test.c" -o "$tmp/route-test"
timeout 30 "$tmp/route-test"
