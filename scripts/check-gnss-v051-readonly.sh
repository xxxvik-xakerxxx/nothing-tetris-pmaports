#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
project_root=$(CDPATH= cd -- "$repo_root/../.." && pwd)
source_tree=${GNSS_SOURCE_TREE:-$project_root/upstream/android_kernel_modules_nothing_mt6878}
source_commit=e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
kernel_pkg="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
device_pkg="$repo_root/pmaports/device/testing/device-nothing-tetris"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

git -C "$source_tree" cat-file -e "$source_commit^{commit}"
git -C "$source_tree" archive "$source_commit" connectivity/gps/data_link |
	tar -xf - -C "$tmp_dir"

patch -s -p1 -d "$tmp_dir" \
	< "$kernel_pkg/1002-vendor-gnss-linux-6.18-compat.patch.vendor"
patch -s -p1 -d "$tmp_dir" \
	< "$kernel_pkg/1003-vendor-gnss-v051-readonly-uapi.patch.vendor"

CC="${HOSTCC:-${CC:-cc}}" \
	sh "$tmp_dir/connectivity/gps/data_link/tests/run_gpsdl_v051_abi_test.sh"
cmp "$tmp_dir/connectivity/gps/data_link/linux/inc/uapi/gpsdl_v051.h" \
	"$device_pkg/gpsdl_v051.h"

mkdir -p "$tmp_dir/host-include/linux"
cat > "$tmp_dir/host-include/linux/types.h" <<'EOF'
#ifndef _HOST_TEST_LINUX_TYPES_H
#define _HOST_TEST_LINUX_TYPES_H
typedef signed long long __s64;
typedef unsigned int __u32;
#endif
EOF

"${HOSTCC:-${CC:-cc}}" -std=c11 -Wall -Wextra -Werror -pedantic \
	-I"$tmp_dir/host-include" -I"$device_pkg" \
	"$device_pkg/nothing-tetris-gnss-readonly.c" \
	-o "$tmp_dir/nothing-tetris-gnss-readonly"

if "$tmp_dir/nothing-tetris-gnss-readonly" >/dev/null 2>&1; then
	echo "GNSS diagnostic accepted an implicit runtime probe" >&2
	exit 1
fi

"${HOSTCC:-${CC:-cc}}" -std=c11 -Wall -Wextra -Werror -pedantic \
	-I"$tmp_dir/host-include" -I"$device_pkg" \
	"$repo_root/scripts/tests/gnss-readonly-test.c" \
	-o "$tmp_dir/gnss-readonly-test"

for scenario in valid zero-fragments no-argument wrong-argument extra-argument \
	missing regular symlink open-error status-error bootup-error time-error \
	fragments fragments-max zero-time negative-time zero-counter negative-counter \
	close-error; do
	"$tmp_dir/gnss-readonly-test" "$scenario" \
		> "$tmp_dir/stdout" 2> "$tmp_dir/stderr"
	case "$scenario" in
	valid|zero-fragments)
		grep -qx 'cipher_key=redacted' "$tmp_dir/stdout"
		test ! -s "$tmp_dir/stderr"
		;;
	*)
		test ! -s "$tmp_dir/stdout"
		test -s "$tmp_dir/stderr"
		;;
	esac
	if grep -Eq '305419896|12345678' "$tmp_dir/stdout" "$tmp_dir/stderr"; then
		echo "GNSS diagnostic disclosed cipher key" >&2
		exit 1
	fi
done

echo "GNSS v051 ABI and 19 isolated diagnostic scenarios passed"
