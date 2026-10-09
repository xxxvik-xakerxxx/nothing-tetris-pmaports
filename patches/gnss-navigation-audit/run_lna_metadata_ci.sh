#!/bin/sh
# CI-only native fixture; no driver loading or hardware query.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" "$directory/test_lna_metadata_patch.py"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/test_lna_metadata.c" -o "$temporary/test-lna-metadata"
"$temporary/test-lna-metadata"
PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" "$directory/test_lna_metadata_patch.py" \
    --emit-owner-fixture "$temporary/lna-owner-under-test.inc"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer -I "$temporary" \
    "$directory/test_lna_owner.c" -o "$temporary/test-lna-owner"
"$temporary/test-lna-owner"
