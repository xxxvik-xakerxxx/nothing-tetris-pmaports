#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'CI-only native fixture; local compilation/execution refused' >&2
    exit 2
fi
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 0 ]; then
    [ "$(uname -s)" = Linux ] || exit 2
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g -O1 -pthread \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        "$directory/b41_agps_decode.c" "$directory/b41_agps_receiver.c" \
        "$directory/b41_agps_native.c" "$directory/test_receiver.c" \
        -Wl,--wrap=b41_agps_native_associate -Wl,--wrap=b41_agps_native_deliver \
        -Wl,--wrap=b41_agps_native_admit \
        -o "$temporary/test-receiver"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
        UBSAN_OPTIONS=halt_on_error=1 timeout 30 "$temporary/test-receiver"
elif [ "$#" -eq 2 ] && [ "$1" = --bionic-compile ]; then
    : "${BIONIC_CC:?Set API28 AArch64 Bionic compiler}"
    "$BIONIC_CC" -std=c11 -Wall -Wextra -Werror -O1 -pthread \
        "$directory/b41_agps_decode.c" "$directory/b41_agps_receiver.c" \
        "$directory/b41_agps_native.c" "$directory/../b41_library_association.c" \
        "$directory/test_receiver.c" \
        -Wl,--wrap=b41_agps_native_associate -Wl,--wrap=b41_agps_native_deliver \
        -Wl,--wrap=b41_agps_native_admit -o "$2"
else
    echo 'usage: run_ci.sh [--bionic-compile OUTPUT]' >&2
    exit 2
fi
