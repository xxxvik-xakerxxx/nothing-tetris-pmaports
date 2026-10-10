#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native slot0 ADC builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -gt 1 ]; then
    echo 'usage: run_slot0_adc_ci.sh [new-output-directory]' >&2
    exit 2
fi
if [ "$#" -eq 1 ]; then
    out=$1
    mkdir "$out"
else
    out=$(mktemp -d)
    trap 'rm -rf "$out"' EXIT HUP INT TERM
fi
timeout --signal=TERM --kill-after=2 120 "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_slot0_adc.c" "$here/test_b41_slot0_adc.c" -o "$out/test_slot0_adc"
timeout --signal=TERM --kill-after=2 20 "$out/test_slot0_adc"
