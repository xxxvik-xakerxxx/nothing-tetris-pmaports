#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

if [ "$#" -ne 5 ]; then
    echo "usage: $0 runtime-extraction verified-isolation-root ci-test-directory first-config|first-queries new-output-directory" >&2
    exit 2
fi
runtime=$1
isolation=$2
tests=$3
fixture=$4
out=$5
case "$fixture" in
    first-config|first-queries) ;;
    *) echo 'only standalone configuration fixtures are accepted' >&2; exit 2 ;;
esac
if [ -e "$out" ]; then
    echo 'refusing to replace an existing isolation root' >&2
    exit 1
fi
check() {
    actual=$(shasum -a 256 "$1" | cut -d ' ' -f 1)
    if [ "$actual" != "$2" ]; then
        echo "pinned runtime hash mismatch: $1" >&2
        exit 1
    fi
}
check "$runtime/runtime-apex/linker64" 4a8dd94eb2d0e59184247892ba5232f7dcbe88eb8c5a43e3a9e4c9c4d4ba7844
check "$runtime/runtime-apex/lib64/bionic/libc.so" 1e365bc2da9ca1e830801ce49f389e6e7fcbc0be7d82824924026af8751f8648
check "$runtime/runtime-apex/lib64/bionic/libm.so" 25c852fca54f103e1a8ac2785a51ef2db2ea21ae9a89295d156ec63cbeb90e40
check "$runtime/runtime-apex/lib64/bionic/libdl.so" ec8a5f55630b6b41ad94b8bbdc6da308e36903709ce759bf2a3a59640715ae32
(cd "$isolation" && shasum -a 256 -c SHA256SUMS)
(cd "$tests" && shasum -a 256 -c SHA256SUMS)
grep -Fxq 'mode=callback-tests-no-vendor-engine' "$tests/BUILD-MANIFEST"
binary="$tests/b41-$fixture-test"
test -f "$binary"
if grep -q 'NEEDED.*libmnl' "$binary.DYNAMIC"; then
    echo 'configuration fixture must not link the vendor engine' >&2
    exit 1
fi
mkdir "$out"
install -d "$out/apex/com.android.runtime/bin" "$out/apex/com.android.runtime/lib64/bionic"
install -d "$out/system/lib64" "$out/vendor/lib64" "$out/proc"
install -m 755 "$runtime/runtime-apex/linker64" "$out/apex/com.android.runtime/bin/linker64"
for name in libc.so libm.so libdl.so; do
    install -m 644 "$runtime/runtime-apex/lib64/bionic/$name" "$out/apex/com.android.runtime/lib64/bionic/$name"
done
install -m 755 "$isolation/launcher" "$out/launcher"
# These two main(void) fixtures ignore the launcher's legacy library argument.
# No vendor library is staged; its load-only launcher and restrictions stay intact.
install -m 755 "$binary" "$out/probe"
install -m 644 "$tests/BUILD-MANIFEST" "$out/BUILD-MANIFEST"
printf 'fixture=%s\nmode=standalone-no-vendor-engine\n' "$fixture" > "$out/TEST-MANIFEST"
(
    cd "$out"
    shasum -a 256 launcher probe apex/com.android.runtime/bin/linker64 \
        apex/com.android.runtime/lib64/bionic/libc.so apex/com.android.runtime/lib64/bionic/libm.so \
        apex/com.android.runtime/lib64/bionic/libdl.so BUILD-MANIFEST TEST-MANIFEST > SHA256SUMS
)
echo 'Standalone configuration fixture staged; no engine or hardware operation performed'
