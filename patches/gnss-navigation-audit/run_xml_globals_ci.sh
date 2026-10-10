#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native XML global builds are CI-only.' >&2
    exit 2
fi
if [ "$#" -ne 2 ] && [ "$#" -ne 3 ]; then
    echo 'usage: run_xml_globals_ci.sh libmnl.so MNL_Config.xml [new-output-directory]' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 3 ]; then
    out=$3
    mkdir "$out" # Retain standalone fixture for a SEPARATE oracle CI step.
else
    out=$(mktemp -d)
    trap 'rm -rf "$out"' EXIT HUP INT TERM
fi
# Dependency flags intentionally split into compiler arguments.
# shellcheck disable=SC2046
timeout --signal=TERM --kill-after=2 120 "${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    $(pkg-config --cflags libxml-2.0 libcrypto) \
    "$here/b41_xml_config.c" "$here/b41_xml_globals.c" \
    "$here/test_b41_xml_globals.c" $(pkg-config --libs libxml-2.0 libcrypto) -lm \
    -o "$out/test_xml_globals"
for feature in CoTMS SwitchTIA GLP GnssMode IFB GGTO L1Only DisableSignal MDTime \
    Time_Source Bluesky GNSSPower SignalConfig OSNMA; do
    timeout --signal=TERM --kill-after=2 20 "$out/test_xml_globals" "$1" "$2" "$feature" > "$out/$feature.bin"
    printf 'PASS: native XML global owner and faults %s\n' "$feature"
done
for chip in 6637 6686; do
    timeout --signal=TERM --kill-after=2 20 "$out/test_xml_globals" "$1" "$2" DCB "$chip" > "$out/DCB-$chip.bin"
    printf 'PASS: native XML DCB owner and faults chip=%s\n' "$chip"
done
