#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

docker run --rm --privileged \
	--ulimit nofile=65535:65535 \
	-v "$repo_root:/work" \
	-w /work \
	alpine:3.23.3 \
	sh -lc '
		set -eu
		ulimit -n 65535
		export CCACHE_DISABLE=1
		export JOBS=4
		export MAKEFLAGS=-j4
		apk add --no-cache \
			build-base bzip2 coreutils cryptsetup dosfstools e2fsprogs-extra \
			file findutils git linux-headers mtools multipath-tools openssl \
			openssl-dev parted patch py3-yaml python3 rsync sfdisk sudo tar \
			util-linux xz zstd

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
			/work/upstream/pmaports/device/testing/firmware-nothing-tetris \
			/work/upstream/pmaports/device/testing/linux-postmarketos-mediatek-mt6878
		rsync -a /work/pmaports/device/testing/device-nothing-tetris/ \
			/work/upstream/pmaports/device/testing/device-nothing-tetris/
		rsync -a /work/pmaports/device/testing/firmware-nothing-tetris/ \
			/work/upstream/pmaports/device/testing/firmware-nothing-tetris/
		rsync -a /work/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/ \
			/work/upstream/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/

		mkdir -p /work/local/pmbootstrap-work/cache_git
		printf "8\n" > /work/local/pmbootstrap-work/version

		cd /work/upstream/pmbootstrap
		./pmbootstrap.py --as-root --work /work/local/pmbootstrap-work -c /work/ci/pmbootstrap-aarch64.cfg checksum \
			device-nothing-tetris firmware-nothing-tetris linux-postmarketos-mediatek-mt6878
		./pmbootstrap.py --as-root --work /work/local/pmbootstrap-work -c /work/ci/pmbootstrap-aarch64.cfg build \
			device-nothing-tetris
		./pmbootstrap.py --as-root --work /work/local/pmbootstrap-work -c /work/ci/pmbootstrap-aarch64.cfg build \
			linux-postmarketos-mediatek-mt6878
		./pmbootstrap.py --as-root --work /work/local/pmbootstrap-work -c /work/ci/pmbootstrap-aarch64.cfg install \
			--android-recovery-zip --password 147147
	'
