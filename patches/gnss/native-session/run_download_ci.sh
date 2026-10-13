#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
    printf '%s\n' 'Retained download compilation and native fixtures are GitHub CI-only.' >&2
    exit 2
fi
[ "$#" -eq 2 ] || { printf '%s\n' 'usage: run_download_ci.sh AARCH64_MUSL_CC OUTPUT' >&2; exit 2; }
compiler=$1
artifact=$2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dsp=$here/../../gnss-navigation-audit/dsp-download
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

# Preserve the existing real selector/ACK and musl/toolchain admission gates.
sh "$dsp/live-inputs/run-ci.sh" "$compiler" "$work/nominal-baseline"
cc=${CC:-clang}
flags='-std=c11 -O1 -g -Wall -Wextra -Werror -Wconversion -Wshadow -frounding-math -ffp-contract=off -fsanitize=address,undefined -fno-omit-frame-pointer'
"$cc" $flags -DB41_NATIVE_L1_RUNNER -DB41_NATIVE_L1_RETAINED_SESSION \
    -Dmain=b41_retained_main -c "$dsp/live-inputs/selectors.c" -o "$work/retained-main.o"
"$cc" $flags "$work/retained-main.o" "$here/test_download_cli.c" "$here/session.c" \
    "$dsp/../b41_capability_branch.c" "$dsp/wire.c" "$dsp/clock.c" \
    "$dsp/bootstrap_fields.c" "$dsp/bootstrap.c" "$dsp/download.c" "$dsp/download_linux.c" \
    -Wl,--wrap=open -Wl,--wrap=fstat -Wl,--wrap=fcntl -Wl,--wrap=pread -Wl,--wrap=close \
    -Wl,--wrap=clock_gettime -Wl,--wrap=ioctl -Wl,--wrap=nanosleep -Wl,--wrap=pause \
    -Wl,--wrap=b41_session_attach -Wl,--wrap=b41_download_linux_step \
    -Wl,--wrap=b41_session_wait_step -Wl,--wrap=b41_session_stop_begin \
    -Wl,--wrap=b41_session_stop_step -lm -o "$work/retained-fixture"
timeout 20 "$work/retained-fixture"

mkdir -p "$(dirname -- "$artifact")"
"$compiler" -std=c11 -static -DB41_NATIVE_L1_RUNNER -DB41_NATIVE_L1_RETAINED_SESSION -O2 \
    -Wall -Wextra -Werror -Wconversion -Wshadow -frounding-math -ffp-contract=off \
    "$dsp/../b41_capability_branch.c" "$dsp/live-inputs/selectors.c" \
    "$dsp/wire.c" "$dsp/clock.c" "$dsp/bootstrap_fields.c" "$dsp/bootstrap.c" \
    "$dsp/download.c" "$dsp/download_linux.c" "$here/session.c" -lm -o "$artifact"
"${READELF:-readelf}" -h "$artifact" > "$work/header"
"${READELF:-readelf}" -l "$artifact" > "$work/programs"
"${READELF:-readelf}" -d "$artifact" > "$work/dynamic"
grep -q 'Machine:.*AArch64' "$work/header"
if grep -q INTERP "$work/programs" || grep -q NEEDED "$work/dynamic"; then
    printf '%s\n' 'Expected standalone static AArch64 retained owner.' >&2
    exit 1
fi
