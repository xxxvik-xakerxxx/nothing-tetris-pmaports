#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

usage() {
	echo "usage: $0 /path/to/downloaded-artifacts [expected-github-sha]" >&2
	exit 2
}

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage

artifact_dir=${1%/}
expected_sha=${2:-}

[ -d "$artifact_dir" ] || {
	echo "artifact directory is missing: $artifact_dir" >&2
	exit 1
}

find_one() {
	name=$1
	matches=$(find "$artifact_dir" -maxdepth 3 -type f -name "$name" -print)
	count=$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')
	if [ "$count" != 1 ]; then
		echo "expected exactly one $name below $artifact_dir, found $count" >&2
		printf '%s\n' "$matches" >&2
		exit 1
	fi
	printf '%s\n' "$matches"
}

manifest=$(find_one BUILD-MANIFEST)
sums=$(find_one SHA256SUMS)
boot_img=$(find_one nothing-tetris-boot.img)
root_sparse=$(find_one nothing-tetris-root.sparse.img)
fit_img=$(find_one boot_image.itb)

manifest_dir=$(dirname "$manifest")
[ "$(dirname "$sums")" = "$manifest_dir" ] || {
	echo "BUILD-MANIFEST and SHA256SUMS must be in the same artifact directory" >&2
	exit 1
}
for image in "$boot_img" "$root_sparse" "$fit_img"; do
	[ "$(dirname "$image")" = "$manifest_dir" ] || {
		echo "artifact file is outside manifest directory: $image" >&2
		exit 1
	}
done

require_manifest_key() {
	key=$1
	grep -Eq "^$key=[^[:space:]]+$" "$manifest" || {
		echo "missing or malformed BUILD-MANIFEST key: $key" >&2
		exit 1
	}
}

for key in \
	github_sha \
	pmbootstrap_commit \
	pmaports_commit \
	kernel_release \
	required_uboot_commit \
	required_uboot_sha256; do
	require_manifest_key "$key"
done

github_sha=$(sed -n 's/^github_sha=//p' "$manifest")
if [ -n "$expected_sha" ] && [ "$github_sha" != "$expected_sha" ]; then
	echo "artifact github_sha mismatch: got $github_sha expected $expected_sha" >&2
	exit 1
fi

case "$(sed -n 's/^kernel_release=//p' "$manifest")" in
	6.18.*) ;;
	*)
		echo "unexpected kernel_release in BUILD-MANIFEST" >&2
		exit 1
		;;
esac

(cd "$manifest_dir" && sha256sum -c SHA256SUMS)

test -s "$boot_img" || {
	echo "empty boot image: $boot_img" >&2
	exit 1
}
test -s "$root_sparse" || {
	echo "empty sparse root image: $root_sparse" >&2
	exit 1
}
test -s "$fit_img" || {
	echo "empty FIT payload: $fit_img" >&2
	exit 1
}

root_type=$(file -b "$root_sparse")
case "$root_type" in
	*"Android sparse image"*) ;;
	*)
		echo "root image is not an Android sparse image: $root_type" >&2
		exit 1
		;;
esac

boot_size=$(wc -c < "$boot_img" | tr -d ' ')
root_size=$(wc -c < "$root_sparse" | tr -d ' ')
fit_size=$(wc -c < "$fit_img" | tr -d ' ')

cat <<EOF
CI install artifact verification passed
github_sha=$github_sha
kernel_release=$(sed -n 's/^kernel_release=//p' "$manifest")
required_uboot_commit=$(sed -n 's/^required_uboot_commit=//p' "$manifest")
fastboot_mapping=nothing-tetris-boot.img -> super; nothing-tetris-root.sparse.img -> userdata
sizes=boot:$boot_size root_sparse:$root_size fit:$fit_size
EOF
