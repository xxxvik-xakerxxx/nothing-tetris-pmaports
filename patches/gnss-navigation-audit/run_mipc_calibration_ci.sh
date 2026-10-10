#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native builds are CI-only.' >&2
    exit 2
fi
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pthread \
    ${CFLAGS:--O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer} \
    b41_mipc_calibration.c b41_mipc_checked_tag.c test_b41_mipc_calibration.c \
    -o "$tmp/test_mipc" ${LDFLAGS:-}
timeout --signal=TERM --kill-after=2 20 "$tmp/test_mipc"
