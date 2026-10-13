#!/bin/sh
set -eu
[ "${CI:-}" = true ] && [ "${GITHUB_ACTIONS:-}" = true ] || {
    printf '%s\n' 'Native navigation C execution is GitHub CI-only.' >&2
    exit 1
}
[ "$#" -eq 2 ] || [ "$#" -eq 4 ] || {
    printf '%s\n' 'usage: run-ci.sh LIBMNL MNLD [AARCH64_MUSL_CC OUTPUT]' >&2
    exit 2
}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -B "$here/source_evidence.py" --libmnl "$1" --mnld "$2"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
ulimit -c 0
"${CC:-clang}" -std=c11 -O1 -g -Wall -Wextra -Werror -Wconversion -Wshadow \
    -frounding-math -ffp-contract=off -fno-fast-math \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/navigation.c" "$here/test_navigation.c" -lm -o "$out/navigation-test"
timeout 20 "$out/navigation-test"
if [ "$#" -eq 4 ]; then
    compiler=$3
    artifact=$4
    case $("$compiler" -dumpmachine) in
        aarch64*) ;;
        *) printf '%s\n' 'Expected AArch64 compiler.' >&2; exit 1 ;;
    esac
    printf '%s\n' '#include <features.h>' | "$compiler" -std=c11 -dM -E -x c - > "$out/macros"
    if grep -Eq '^#define[[:space:]]+__GLIBC__([[:space:]]|$)' "$out/macros"; then
        printf '%s\n' 'Expected musl headers, not glibc fallback.' >&2
        exit 1
    fi
    mkdir -p "$(dirname -- "$artifact")"
    "$compiler" -std=c11 -static -O2 -Wall -Wextra -Werror -Wconversion -Wshadow \
        -frounding-math -ffp-contract=off -fno-fast-math \
        "$here/navigation.c" "$here/test_navigation.c" -lm -o "$artifact"
    "${READELF:-readelf}" -h "$artifact" > "$out/header"
    "${READELF:-readelf}" -l "$artifact" > "$out/programs"
    "${READELF:-readelf}" -d "$artifact" > "$out/dynamic"
    grep -q 'Machine:.*AArch64' "$out/header"
    if grep -q INTERP "$out/programs" || grep -q NEEDED "$out/dynamic"; then
        printf '%s\n' 'Expected static AArch64 fixture.' >&2
        exit 1
    fi
fi
