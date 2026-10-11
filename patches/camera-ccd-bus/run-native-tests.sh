#!/bin/sh
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
	printf '%s\n' 'Native C tests are CI-only' >&2
	exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
${CC:-cc} -std=c11 -Wall -Wextra -Werror \
	-I"$here/../camera-composer" -I"$here/../camera-camsv" \
	-I"$here/../camera-ccd-cq" \
	"$here/worker-owner-test.c" -o "$out/worker-owner-test"
"$out/worker-owner-test"
${CC:-cc} -std=c11 -Wall -Wextra -Werror \
	-I"$here/../camera-composer" -I"$here/../camera-camsv" \
	-I"$here/../camera-ccd-cq" \
	-c "$here/ccd-worker-owner.c" -o "$out/ccd-worker-owner.o"
printf '%s\n' 'PASS: native worker registration/retirement faults (no hardware)'
