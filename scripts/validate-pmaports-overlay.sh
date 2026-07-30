#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
kernel_pkg="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
device_pkg="$repo_root/pmaports/device/testing/device-nothing-tetris"
firmware_pkg="$repo_root/pmaports/device/testing/firmware-nothing-tetris"

validate_sums() {
	pkgdir=$1
	awk '
		BEGIN { in_sums = 0 }
		/^sha512sums="/ { in_sums = 1; next }
		in_sums && /^"$/ { exit }
		in_sums && NF >= 2 { print $1 "  " $2 }
	' "$pkgdir/APKBUILD" |
	while read -r expected file; do
		case "$file" in
			http://*|https://*|*::*|*.tar|*.tar.*)
				continue
				;;
		esac

		if [ ! -f "$pkgdir/$file" ]; then
			echo "missing source: $pkgdir/$file" >&2
			return 1
		fi

		actual=$(sha512sum "$pkgdir/$file" | awk '{ print $1 }')
		if [ "$actual" != "$expected" ]; then
			echo "checksum mismatch: $pkgdir/$file" >&2
			echo "expected: $expected" >&2
			echo "actual:   $actual" >&2
			return 1
		fi
	done
}

validate_source_files() {
	pkgdir=$1
	awk '
		BEGIN { in_source = 0 }
		/^source="/ { in_source = 1; next }
		in_source && /^"$/ { exit }
		in_source && NF >= 1 { print $1 }
	' "$pkgdir/APKBUILD" |
	while read -r source; do
		case "$source" in
			http://*|https://*|*::*|\$*)
				continue
				;;
		esac

		if [ ! -f "$pkgdir/$source" ]; then
			echo "missing source entry: $pkgdir/$source" >&2
			return 1
		fi
	done
}

validate_sums "$kernel_pkg"
validate_sums "$device_pkg"
validate_sums "$firmware_pkg"
validate_source_files "$kernel_pkg"
validate_source_files "$device_pkg"
validate_source_files "$firmware_pkg"

echo "pmaports overlay validation passed"
