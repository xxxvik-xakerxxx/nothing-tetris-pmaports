#!/bin/sh
# Native compilation is CI-only. No live resources used by this test.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer "$here/capture-test.c" -o "$tmp/capture-test"
"$tmp/capture-test"
