#!/bin/sh
# CI-only: source stack then actual patched helper with poisoned state fixture.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" "$directory/test_lna_control_gate.py"
PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" "$directory/test_lna_control_gate.py" \
    --emit-control-fixture "$temporary/lna-control-under-test.inc"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -I "$temporary" \
    "$directory/test_lna_control_gate.c" -o "$temporary/test-lna-control"
"$temporary/test-lna-control"
