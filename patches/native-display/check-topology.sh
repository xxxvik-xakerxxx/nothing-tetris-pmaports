#!/bin/sh
set -eu
test "$#" -eq 1 || { echo "usage: $0 linux-source-tree" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
sh "$here/prepare-topology.sh" "$1" "$tmp/base"
cp -R "$tmp/base" "$tmp/candidate"
(cd "$tmp/candidate" && git apply --check "$here/0003-mt6878-postmask-topology.patch")
(cd "$tmp/candidate" && git apply "$here/0003-mt6878-postmask-topology.patch")
for version in base candidate; do
    cp "$tmp/$version/drivers/soc/mediatek/mt6878-mmsys.h" "$tmp/$version-route.h"
    awk '/static const unsigned int mt6878_mtk_ddp_main\[\]/ { active=1 }
         active { print } active && /^};/ { exit }' \
        "$tmp/$version/drivers/gpu/drm/mediatek/mtk_drm_drv.c" > "$tmp/$version-path.h"
done
awk '/^#define MT6878_MUTEX_MOD_/ { print }
     /static const u8 mt6878_mutex_mod\[/ { active=1 }
     active { print } active && /^};/ { exit }' \
    "$tmp/candidate/drivers/soc/mediatek/mtk-mutex.c" > "$tmp/mutex.h"
grep -hoE 'DDP_COMPONENT_[A-Z0-9_]+' "$tmp/candidate-route.h" "$tmp/mutex.h" |
    sort -u | grep -v '^DDP_COMPONENT_ID_MAX$' |
    awk 'BEGIN { print "enum {" } { print $0 "," } END { print "DDP_COMPONENT_ID_MAX };" }' \
    > "$tmp/components.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/topology-test.c" -o "$tmp/topology-test"
"$tmp/topology-test"
# Ensure a mutation to the proven working route is detected.
sed 's/0x00010001/0x00050005/' "$tmp/candidate-route.h" > "$tmp/mutant.h"
mv "$tmp/mutant.h" "$tmp/candidate-route.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/topology-test.c" -o "$tmp/topology-mutant"
ulimit -c 0
if "$tmp/topology-mutant" > "$tmp/mutant.out" 2>&1; then
    echo 'FAIL: changed display route was accepted' >&2
    exit 1
fi
echo 'PASS: rejected incorrect PQ route (host checks, not DT or hardware validation)'
