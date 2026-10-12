#!/bin/sh
# Native fixtures only in CI; Bionic compile/link produces an unexecuted artifact.
set -eu
if [ "${CI:-}" != true ]; then echo 'Native receiver-policy fixtures are CI-only.' >&2; exit 2; fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 0 ]; then
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    timeout --signal=TERM --kill-after=2 60 "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        "$here/b41_receiver_properties.c" "$here/b41_receiver_policy.c" \
        "$here/b41_startup_adapter.c" "$here/test_b41_receiver_policy.c" \
        -Wl,--wrap=b41_receiver_property_read -o "$temporary/test-receiver-policy"
    timeout --signal=TERM --kill-after=2 20 "$temporary/test-receiver-policy"
elif [ "$#" -eq 2 ] && [ "$1" = --bionic-compile ]; then
    : "${BIONIC_CC:?set actual ARM64 Bionic compiler, e.g. aarch64-linux-android28-clang}"
    timeout --signal=TERM --kill-after=2 60 "$BIONIC_CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$here/b41_receiver_properties.c" "$here/b41_receiver_policy.c" \
        "$here/b41_startup_adapter.c" "$here/test_b41_receiver_policy.c" \
        -Wl,--wrap=b41_receiver_property_read -Wl,--wrap=__system_property_get -o "$2"
else
    echo 'usage: run_receiver_policy_ci.sh [--bionic-compile OUTPUT]' >&2
    exit 2
fi
