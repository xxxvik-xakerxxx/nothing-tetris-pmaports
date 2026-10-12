#!/bin/sh
# CI only: actual Unix datagram delivery/ownership, no GNSS devices or engine.
set -eu
if [ "${CI:-}" != true ]; then echo 'Native AGPS fixtures are CI-only.' >&2; exit 2; fi
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
timeout --signal=TERM --kill-after=2 60 "${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_agps_host.c" "$directory/test_b41_agps_host.c" \
    -Wl,--wrap=send -o "$temporary/test-agps-host"
timeout --signal=TERM --kill-after=2 20 "$temporary/test-agps-host"
timeout --signal=TERM --kill-after=2 60 "${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_agps_endpoint.c" "$directory/b41_agps_host.c" \
    "$directory/test_b41_agps_endpoint.c" \
    -Wl,--wrap=lstat -Wl,--wrap=socket -Wl,--wrap=connect -Wl,--wrap=close \
    -Wl,--wrap=getsockopt -Wl,--wrap=getpeername -Wl,--wrap=fstat \
    -o "$temporary/test-agps-endpoint"
timeout --signal=TERM --kill-after=2 20 "$temporary/test-agps-endpoint"
