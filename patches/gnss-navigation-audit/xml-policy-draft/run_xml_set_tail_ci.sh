#!/bin/sh
set -eu
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
if [ "${CI:-}" != true ]; then
    echo 'XML SET tail native compilation is CI-only.' >&2; exit 2
fi
if [ "$#" -ne 1 ]; then
    echo 'usage: run_xml_set_tail_ci.sh NEW_OUTPUT_DIRECTORY' >&2; exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$1
test ! -e "$out"
mkdir -p "$out"
timeout --signal=TERM --kill-after=2 120 "${CC:-cc}" -std=c11 -O1 -g -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer \
    "$here/b41_xml_set_tail.c" "$here/test_b41_xml_set_tail.c" -lm -o "$out/test_xml_set_tail"
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
    timeout --signal=TERM --kill-after=2 20 "$out/test_xml_set_tail"
sha256sum "$out/test_xml_set_tail" > "$out/SHA256SUMS"
echo 'PASS: native XML SET serializer fixtures, no vendor calls.'
