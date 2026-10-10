#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Slot6 service builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_slot6_service.c" "$here/b41_startup_adapter.c" \
    "$here/b41_agps_host.c" "$here/b41_navigation_output.c" \
    "$here/b41_frame_worker.c" \
    "$here/test_b41_slot6_service.c" -o "$out/test_slot6_service"
timeout --signal=TERM --kill-after=2 20 "$out/test_slot6_service"
