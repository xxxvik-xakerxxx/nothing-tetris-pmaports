#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native compilation/execution is restricted to parent-owned CI.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
    --bionic-compile)
        [ "$#" -eq 2 ]
        : "${BIONIC_CC:?set BIONIC_CC to the pinned NDK compiler}"
        "$BIONIC_CC" -std=c11 -Wall -Wextra -Werror -O2 \
            "$here/../b41_first_config.c" \
            "$here/b41_native_satellite_config.c" \
            "$here/test_native_satellite_config.c" -o "$2"
        ;;
    '')
        build=$(mktemp -d)
        trap 'rm -rf "$build"' EXIT HUP INT TERM
        "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -O1 -g \
            -fsanitize=address,undefined -fno-omit-frame-pointer \
            "$here/../b41_first_config.c" \
            "$here/b41_native_satellite_config.c" \
            "$here/test_native_satellite_config.c" -o "$build/test"
        "$build/test"
        ;;
    *) echo 'usage: run_ci.sh [--bionic-compile OUTPUT]' >&2; exit 2 ;;
esac
