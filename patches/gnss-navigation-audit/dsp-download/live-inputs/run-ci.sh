#!/bin/sh
set -eu
[ "${CI:-}" = true ] && [ "${GITHUB_ACTIONS:-}" = true ] || {
    printf '%s\n' 'Native fixtures are CI-only.' >&2
    exit 1
}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/../../b41_capability_branch.c" "$here/selectors.c" \
    "$here/../wire.c" "$here/../clock.c" "$here/../bootstrap_fields.c" \
    "$here/../bootstrap.c" "$here/../download.c" "$here/../download_linux.c" \
    "$here/test_selectors.c" -lm \
    -Wl,--wrap=clock_gettime -Wl,--wrap=fcntl -Wl,--wrap=fstat -Wl,--wrap=ioctl \
    -o "$out/test-selectors"
timeout 20 "$out/test-selectors"

# Block all acquisition in CLI argument fixtures, including accidental regressions.
"${CC:-clang}" -std=c11 -DB41_NATIVE_L1_RUNNER -DB41_NATIVE_L1_CLI_FIXTURE -O1 -g \
    -Wall -Wextra -Werror -Wconversion -Wshadow \
    -frounding-math -ffp-contract=off -fsanitize=address,undefined \
    "$here/../../b41_capability_branch.c" "$here/selectors.c" \
    "$here/../wire.c" "$here/../clock.c" "$here/../bootstrap_fields.c" \
    "$here/../bootstrap.c" "$here/../download.c" "$here/../download_linux.c" \
    "$here/test_selectors.c" -Wl,--wrap=open -Wl,--wrap=ioctl \
    -lm -o "$out/test-runner-help"
timeout 20 "$out/test-runner-help" --help > "$out/help"
grep -Fxq 'usage: gnss-l1-nominal GPS_PHYSICAL_PROFILE [TIMEOUT_MS:1..30000]' "$out/help"

expect_usage_rejection() {
    result=0
    timeout 20 "$out/test-runner-help" "$@" > "$out/rejected-out" 2> "$out/rejected-err" || result=$?
    [ "$result" -eq 2 ] && [ ! -s "$out/rejected-out" ] && [ ! -s "$out/rejected-err" ] || {
        printf 'Expected device-free argument rejection, got status=%s\n' "$result" >&2
        exit 1
    }
}
expect_usage_rejection
expect_usage_rejection --help 1
expect_usage_rejection --help extra extra
expect_usage_rejection --unknown
expect_usage_rejection ''
expect_usage_rejection profile 1 extra
for invalid_timeout in '' 0 30001 -1 +1 ' 1' 1x 999999999999999999999999; do
    expect_usage_rejection profile "$invalid_timeout"
done

if [ "$#" -eq 0 ] && [ -n "${GNSS_NATIVE_MUSL_CC:-}" ]; then
    set -- "$GNSS_NATIVE_MUSL_CC" "${GNSS_NATIVE_OUTPUT:-out/gnss-l1-nominal}"
fi

if [ "$#" -ne 0 ]; then
    [ "$#" -eq 2 ] || { printf '%s\n' 'usage: run-ci.sh [AARCH64_MUSL_CC OUTPUT]' >&2; exit 2; }
    compiler=$1
    artifact=$2
    mkdir -p "$(dirname -- "$artifact")"
    case $("$compiler" -dumpmachine) in
        aarch64*) ;;
        *) printf '%s\n' 'Expected AArch64 toolchain.' >&2; exit 1 ;;
    esac
    # musl-gcc reports its underlying GNU target. Check the selected headers,
    # not the wrapper name or that target's libc suffix.
    printf '%s\n' '#include <features.h>' | \
        "$compiler" -std=c11 -dM -E -x c - > "$out/compiler-macros"
    if grep -Eq '^#define[[:space:]]+__GLIBC__([[:space:]]|$)' "$out/compiler-macros"; then
        printf '%s\n' 'Expected musl headers; compiler selected glibc.' >&2
        exit 1
    fi
    "$compiler" -std=c11 -static -DB41_NATIVE_L1_RUNNER -O2 \
        -Wall -Wextra -Werror -Wconversion -Wshadow \
        -frounding-math -ffp-contract=off \
        "$here/../../b41_capability_branch.c" "$here/selectors.c" \
        "$here/../wire.c" "$here/../clock.c" "$here/../bootstrap_fields.c" \
        "$here/../bootstrap.c" "$here/../download.c" "$here/../download_linux.c" \
        -lm -o "$artifact"
    "${READELF:-readelf}" -h "$artifact" > "$out/elf-header"
    "${READELF:-readelf}" -l "$artifact" > "$out/elf-programs"
    "${READELF:-readelf}" -d "$artifact" > "$out/elf-dynamic"
    grep -q 'Machine:.*AArch64' "$out/elf-header"
    if grep -q 'INTERP' "$out/elf-programs" || grep -q 'NEEDED' "$out/elf-dynamic"; then
        printf '%s\n' 'Expected standalone static AArch64 binary.' >&2
        exit 1
    fi
fi
