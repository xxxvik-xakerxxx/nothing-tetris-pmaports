#!/bin/sh
# Pure configuration fixture: no Android property service or vendor engine.
set -eu
if [ "${CI:-}" != true ]; then echo 'Native receiver-input fixtures are CI-only.' >&2; exit 2; fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 0 ]; then
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    timeout --signal=TERM --kill-after=2 60 "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        "$here/b41_receiver_inputs.c" "$here/b41_startup_adapter.c" \
        "$here/test_b41_receiver_inputs.c" -o "$temporary/test-receiver-inputs"
    timeout --signal=TERM --kill-after=2 20 "$temporary/test-receiver-inputs"
elif [ "$#" -eq 2 ] && [ "$1" = --bionic-compile ]; then
    : "${BIONIC_CC:?set actual ARM64 Bionic compiler}"
    timeout --signal=TERM --kill-after=2 60 "$BIONIC_CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$here/b41_receiver_inputs.c" "$here/b41_startup_adapter.c" \
        "$here/test_b41_receiver_inputs.c" -o "$2"
else
    echo 'usage: run_receiver_inputs_ci.sh [--bionic-compile OUTPUT]' >&2
    exit 2
fi
