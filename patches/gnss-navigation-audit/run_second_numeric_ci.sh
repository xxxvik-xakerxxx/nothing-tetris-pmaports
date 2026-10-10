#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then echo 'Native builds are CI-only.' >&2; exit 2; fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_second_numeric.c" "$here/b41_capability_branch.c" \
    "$here/test_b41_second_numeric.c" -o "$out/test_second_numeric"
timeout --signal=TERM --kill-after=2 20 "$out/test_second_numeric"
