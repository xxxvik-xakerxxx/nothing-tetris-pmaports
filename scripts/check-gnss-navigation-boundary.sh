#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
audit_dir="$repo_root/patches/gnss-navigation-audit"
cc=${HOSTCC:-${CC:-cc}}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

test -d "$audit_dir"

if find "$audit_dir" -type f \( -name mnld -o -name libmnl.so \) | grep -q .; then
	echo "proprietary GNSS binaries must not be stored in the audit tree" >&2
	exit 1
fi

grep -Fq '3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90' \
	"$audit_dir/README.md"
grep -Fq '285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83' \
	"$audit_dir/README.md"
grep -Fq 'start sequence, measurement decoder, position ABI, and position fix are NOT proven' \
	"$audit_dir/README.md"

if grep -Eq '(^|[^[:alnum:]_])(open|close|ioctl|read|write|mmap)[[:space:]]*\(' \
		"$audit_dir/b41_nmea_boundary.h" \
		"$audit_dir/b41_frame_sync.h"; then
	echo "offline GNSS boundary headers must not access devices or mappings" >&2
	exit 1
fi

"$cc" -std=c11 -Wall -Wextra -Werror -pedantic \
	-I "$audit_dir" "$audit_dir/test_b41_nmea_boundary.c" \
	-o "$tmp/test-b41-nmea-boundary"
"$tmp/test-b41-nmea-boundary"

"$cc" -std=c11 -Wall -Wextra -Werror -pedantic \
	-I "$audit_dir" "$audit_dir/test_b41_frame_sync.c" \
	-o "$tmp/test-b41-frame-sync"
"$tmp/test-b41-frame-sync" > "$tmp/frame-sync-vectors"
grep -Fxq '24504d544b3733382c302a32320d' "$tmp/frame-sync-vectors"
grep -Fxq '24504d544b3733382c3235352a32300d' "$tmp/frame-sync-vectors"
grep -Fxq '24504d544b3733362c302c302a33300d' "$tmp/frame-sync-vectors"

echo "PASS: GNSS navigation ABI boundary is offline, bounded, and hash-pinned"
