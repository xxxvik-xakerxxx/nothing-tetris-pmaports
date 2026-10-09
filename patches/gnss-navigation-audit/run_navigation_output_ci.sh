#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native navigation-service builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
for fixture in navigation_output frame_worker; do
    case "$fixture" in
        navigation_output) wrap=-Wl,--wrap=write ;;
        frame_worker) wrap=-Wl,--wrap=send ;;
    esac
    "${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
        -fsanitize=address,undefined -fno-omit-frame-pointer -I"$here" \
        "$here/b41_startup_adapter.c" "$here/b41_agps_host.c" \
        "$here/b41_navigation_output.c" "$here/b41_frame_worker.c" \
        "$here/test_b41_$fixture.c" "$wrap" -o "$out/test_$fixture"
    timeout --signal=TERM --kill-after=2 20 "$out/test_$fixture"
done
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_gpsdl_identity.c" "$here/test_b41_gpsdl_identity.c" -o "$out/test_gpsdl_identity"
"$out/test_gpsdl_identity"
