#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I"$here/../camera-seninf" \
    -I"$here/../camera-seninf-route" "$here/controller-test.c" -o "$out/test"
timeout --signal=TERM --kill-after=2 30 "$out/test"
