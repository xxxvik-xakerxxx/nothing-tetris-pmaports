#!/bin/sh
# CI only: do not compile native sources on the local host.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer "$here/contract-test.c" -o "$tmp/contract-test"
"$tmp/contract-test"
