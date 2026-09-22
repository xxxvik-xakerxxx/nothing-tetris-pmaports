#!/bin/sh
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=${1:?usage: build-ci.sh /absolute/output-directory}
mkdir -p "$dest"
cd "$dest"
curl -fL --retry 2 -o source.tar.gz \
  https://gitlab.freedesktop.org/hadess/iio-sensor-proxy/-/archive/3.9/iio-sensor-proxy-3.9.tar.gz
printf '%s  source.tar.gz\n' a89c842f8db2a1a36c1c7c990434bb57fd905224459170cba2ec56e79f1272acc4cac4221937704d5e9247f957d86fde716d25e2d1ccb80d88fa643b47edfda6 | sha512sum -c -
tar -xzf source.tar.gz
cd iio-sensor-proxy-3.9
patch -p1 < "$src/0001-register-hf-backend.patch"
cp "$src/drv-mtk-hf.c" "$src/hf-abi.h" src/
meson setup output --prefix=/usr --libexecdir=libexec \
  -Dudevrulesdir=/usr/lib/udev/rules.d \
  -Dsystemdsystemunitdir=/usr/lib/systemd/system -Dssc-support=enabled
meson compile -C output
meson test --print-errorlogs -C output
cc -std=gnu11 -Wall -Wextra -Werror "$src/test-hf-abi.c" -o output/test-hf-abi
output/test-hf-abi
mkdir -p "$dest/artifact"
cp output/src/iio-sensor-proxy output/src/monitor-sensor "$dest/artifact/"
cp "$src/nothing-tetris-sensor-proxy.service" "$dest/artifact/"
cd "$dest/artifact"
sha256sum iio-sensor-proxy monitor-sensor > SHA256SUMS
printf '%s\n' "${GITHUB_SHA:?CI source commit required}" > source-commit
