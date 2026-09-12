#!/bin/sh
set -eu
test "$#" -eq 1 || { echo "usage: $0 B4.1-device-modules-repository" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
file=drivers/misc/mediatek/ccmni/ccmni.c
git -C "$1" archive ee2be53cb75670b548948636a0db1d1ff112bf12 "$file" \
    drivers/misc/mediatek/rps/rps_perf.c |
    tar -x -C "$tmp"
(cd "$tmp" && git apply --check "$here/0001-ccmni-linux-6.18.patch.vendor")
(cd "$tmp" && git apply "$here/0001-ccmni-linux-6.18.patch.vendor")
(cd "$tmp" && git apply --check "$here/0002-rps-linux-6.18-headers.patch.vendor")
(cd "$tmp" && git apply "$here/0002-rps-linux-6.18-headers.patch.vendor")
awk '/static inline void napi_gro_list_flush\(/ { active=1 }
     active { print } active && /^}/ { exit }' "$tmp/$file" > "$tmp/flush.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/ccmni-gro-test.c" -o "$tmp/test"
"$tmp/test"
sed 's/gro->rx_count = 0/gro->rx_count = 1/' "$tmp/flush.h" > "$tmp/mutant.h"
mv "$tmp/mutant.h" "$tmp/flush.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/ccmni-gro-test.c" -o "$tmp/mutant"
ulimit -c 0
if "$tmp/mutant" > "$tmp/mutant.out" 2>&1; then
    echo 'FAIL: stale GRO count accepted' >&2
    exit 1
fi
echo 'PASS: stale GRO count rejected; host model only'
