#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
volume_name="nothing-cmf-pmbootstrap-arm64"

docker volume create "$volume_name" >/dev/null
docker run --rm --privileged \
	--ulimit nofile=1048576:1048576 \
	-v "$repo_root:/work" \
	-v "$volume_name:/pmwork-arm64" \
	-w /work \
	alpine:3.23.3 \
	sh -lc '
		set -eu
		ulimit -n 1048576
		export CCACHE_DISABLE=1
		export JOBS=1
		export MAKEFLAGS=-j1
		pmbootstrap_work=/pmwork-arm64/work2
		mkdir -p "$pmbootstrap_work"
		test -f /pmwork-arm64/version || printf "8\n" > /pmwork-arm64/version
		test -f "$pmbootstrap_work/version" ||
			printf "8\n" > "$pmbootstrap_work/version"
		mkdir -p "$pmbootstrap_work/cache_distfiles"
		if test -f /work/artifacts/linux-postmarketos-mediatek-mt6878-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz; then
			cp /work/artifacts/linux-postmarketos-mediatek-mt6878-d84b264a54a37611f2f46bc19363cb9b41606205.tar.gz \
				"$pmbootstrap_work/cache_distfiles/"
		fi

		apk add --no-cache \
			build-base bzip2 coreutils cryptsetup dosfstools e2fsprogs-extra \
			file findutils git linux-headers mtools multipath-tools openssl \
			openssl-dev parted patch py3-yaml python3 rsync sfdisk sudo tar \
			util-linux xz zstd >/dev/null

		if ! test -d /work/upstream/pmbootstrap/.git; then
			git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git \
				/work/upstream/pmbootstrap
		fi
		if ! test -d /work/upstream/pmaports/.git; then
			rm -rf /work/upstream/pmaports
			git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmaports.git \
				/work/upstream/pmaports
		fi
		rm -rf \
			/work/upstream/pmaports/device/testing/device-nothing-tetris \
			/work/upstream/pmaports/device/testing/linux-postmarketos-mediatek-mt6878
		rsync -a /work/pmaports/device/testing/device-nothing-tetris/ \
			/work/upstream/pmaports/device/testing/device-nothing-tetris/
		rsync -a /work/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/ \
			/work/upstream/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/

		cd /work/upstream/pmbootstrap
		./pmbootstrap.py --as-root \
			--no-ccache \
			--work "$pmbootstrap_work" \
			-c /work/ci/pmbootstrap-aarch64.cfg \
			checksum linux-postmarketos-mediatek-mt6878
		./pmbootstrap.py --as-root \
			--no-ccache \
			--work "$pmbootstrap_work" \
			-c /work/ci/pmbootstrap-aarch64.cfg \
			build --lax --force \
			linux-postmarketos-mediatek-mt6878 --arch aarch64

		mkdir -p /work/artifacts/apks
		kernel_apk=$(find "$pmbootstrap_work/packages/edge/aarch64" \
			-name "linux-postmarketos-mediatek-mt6878-*.apk" |
			sort -V | tail -n 1)
		test -n "$kernel_apk"
		cp "$kernel_apk" /work/artifacts/apks/
	'
