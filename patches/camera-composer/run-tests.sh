#!/bin/sh
# CI only: do not run a native compile on the development host.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$here" -I"$here/../camera-camsv" \
	"$here/composer-test.c" -o "$tmp/test"
"$tmp/test"
