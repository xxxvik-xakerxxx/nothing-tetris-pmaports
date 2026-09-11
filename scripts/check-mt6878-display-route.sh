#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pkg="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

# Reconstruct the actual packaged header, in APKBUILD order.
awk '/^source="/ { active=1; next } active && /^"$/ { exit }
     active && $1 ~ /\.patch$/ { print $1 }' "$pkg/APKBUILD" |
while read -r patch; do
	if ! grep -Fq '+++ b/drivers/soc/mediatek/mt6878-mmsys.h' "$pkg/$patch"; then
		continue
	fi
	(cd "$tmp" && git apply --include=drivers/soc/mediatek/mt6878-mmsys.h "$pkg/$patch")
done

"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
	"$repo_root/ci/mt6878-display-route-test.c" -o "$tmp/route-test"
"$tmp/route-test"
