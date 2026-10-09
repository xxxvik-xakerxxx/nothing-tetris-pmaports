#!/bin/sh
# CI-only native tests and compile-only real ioctl caller; no /dev operations.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I"$here/../camera-composer" \
    -I"$here/../camera-camsv" "$here/recipe-test.c" -o "$tmp/recipe-test"
"$tmp/recipe-test"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I"$here/../camera-composer" \
    -I"$here/../camera-camsv" "$here/worker-test.c" -o "$tmp/worker-test"
"$tmp/worker-test"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$here/../camera-composer" \
    -I"$here/../camera-camsv" -c "$here/mt6878-camera-ccd-worker.c" \
    -o "$tmp/ccd-worker.o"
