#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'NV calibration builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_nv_calibration.c" "$here/b41_first_config.c" \
    "$here/test_b41_nv_calibration.c" -Wl,--wrap=pread -Wl,--wrap=close \
    -o "$out/test_nv_calibration"
timeout --signal=TERM --kill-after=2 20 "$out/test_nv_calibration"
