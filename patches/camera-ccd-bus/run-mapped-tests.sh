#!/bin/sh
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
	printf '%s\n' 'Native C tests are CI-only' >&2
	exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
compile() {
	${CC:-cc} -std=c11 -Wall -Wextra -Werror \
		-I"$here/../camera-composer" -I"$here/../camera-camsv" -I"$here/../camera-ccd-cq" "$@"
}
compile "$here/mapped-worker-test.c" -o "$out/mapped-worker-test"
"$out/mapped-worker-test"
compile -c "$here/ccd-mapped-worker.c" -o "$out/mapped.o"
compile -c "$here/ccd-worker-owner.c" -o "$out/owner.o"
compile -c "$here/../camera-ccd-cq/mt6878-camera-ccd-worker.c" -o "$out/worker.o"
${CC:-cc} -r "$out/mapped.o" "$out/owner.o" "$out/worker.o" -o "$out/native-path.o"
