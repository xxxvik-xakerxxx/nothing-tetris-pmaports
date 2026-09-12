#!/bin/sh
set -eu

test "$#" -eq 1 || { echo "usage: $0 prepared-linux-tree" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_file="$1/drivers/gpu/drm/mediatek/mtk_ddp_comp.c"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/drivers/gpu/drm/mediatek"
cp "$source_file" "$tmp/drivers/gpu/drm/mediatek/mtk_ddp_comp.c"
patch --batch --fuzz=0 -s -p1 -d "$tmp" < "$here/0001-mt6878-postmask-relay-lifecycle.patch"
awk '/^#define (DISP_REG_POSTMASK|POSTMASK_)/ { print }
     /^static void mtk_postmask_(config|start|stop)\(/ { active=1 }
     active { print }
     active && /^}/ { active=0 }' \
    "$tmp/drivers/gpu/drm/mediatek/mtk_ddp_comp.c" > "$tmp/postmask-source.h"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -Wno-unused-parameter \
    -I"$tmp" "$here/postmask-test.c" -o "$tmp/postmask-test"
"$tmp/postmask-test"
sed 's/^#define POSTMASK_MT6878_RELAY_CFG.*/#define POSTMASK_MT6878_RELAY_CFG 1/' \
    "$tmp/postmask-source.h" > "$tmp/postmask-mutant.h"
mv "$tmp/postmask-mutant.h" "$tmp/postmask-source.h"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -Wno-unused-parameter \
    -I"$tmp" "$here/postmask-test.c" -o "$tmp/postmask-mutant"
ulimit -c 0
if "$tmp/postmask-mutant" > "$tmp/mutant.out" 2>&1; then
    echo 'FAIL: tests accepted the generic configuration for MT6878' >&2
    exit 1
fi
echo 'PASS: rejected wrong MT6878 relay configuration'
printf 'Prepared source blob: '
git hash-object "$source_file"
echo 'PASS: candidate applies without fuzz; host lifecycle checks (not hardware proof)'
