#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pmaports_tree=${1:?usage: apply-pmaports-patches.sh /path/to/pmaports}

for patch in "$repo_root"/pmaports-patches/*.patch; do
	applied=false
	case "${patch##*/}" in
		0000-initramfs-3.12.3.patch)
			if grep -qx 'pkgver=3.12.3' "$pmaports_tree/main/postmarketos-initramfs/APKBUILD" &&
				test -f "$pmaports_tree/main/postmarketos-initramfs/tests/01-parse-cmdline-testlib.sh"; then
				applied=true
			fi
			;;
		0001-initramfs-stable-usb-identity.patch)
			if grep -q '^derive_usb_network_mac_pair()' "$pmaports_tree/main/postmarketos-initramfs/init_functions.sh" &&
				grep -q '^\[variable.usb.usb_network_mac_seed_path\]' "$pmaports_tree/deviceinfo_schema.toml" &&
				test -x "$pmaports_tree/main/postmarketos-initramfs/tests/03-usb-stable-mac.sh"; then
				applied=true
			fi
			;;
		*)
			if git -C "$pmaports_tree" apply --reverse --check "$patch"; then
				applied=true
			fi
			;;
	esac

	if "$applied"; then
		echo "pmaports patch already applied: ${patch##*/}"
		continue
	fi
	git -C "$pmaports_tree" apply --check "$patch" || {
		echo "pmaports patch does not apply cleanly: $patch" >&2
		exit 1
	}
	git -C "$pmaports_tree" apply "$patch"
done
