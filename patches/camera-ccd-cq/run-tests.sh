#!/bin/sh
# Native compilation and fixture execution are CI-only.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer "$here/cq-test.c" -o "$tmp/cq-test"
"$tmp/cq-test"
