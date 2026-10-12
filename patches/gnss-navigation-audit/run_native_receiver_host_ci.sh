#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native receiver-host builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$here/test_b41_engine_registration_shape.py" --source-only
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -O1 -D_FORTIFY_SOURCE=2 -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_startup_adapter.c" "$here/b41_agps_host.c" \
    "$here/b41_navigation_output.c" "$here/b41_frame_worker.c" \
    "$here/b41_native_receiver_host.c" "$here/test_b41_native_receiver_host.c" \
    "$here/native-agps-receiver/b41_agps_decode.c" \
    "$here/native-agps-receiver/b41_agps_receiver.c" \
    "$here/native-agps-receiver/b41_agps_native.c" "$here/b41_library_association.c" \
    -Wl,--wrap=write -o "$out/test_native_receiver_host"
timeout --signal=TERM --kill-after=2 20 "$out/test_native_receiver_host"
