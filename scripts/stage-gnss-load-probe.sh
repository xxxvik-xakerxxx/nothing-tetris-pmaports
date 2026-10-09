#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

if [ "$#" -ne 4 ]; then
    echo "usage: $0 runtime-extraction libmnl.so ci-helper-directory new-output-directory" >&2
    exit 2
fi
runtime=$1
mnl=$2
helpers=$3
out=$4
if [ -e "$out" ]; then
    echo 'refusing to replace existing probe root' >&2
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
check "$runtime/system-cxx" 2267f93b8b3c9d1967f1833d5f71c7312213c43bb291250cf772800763037fb9
check "$mnl" 3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90
(cd "$helpers" && shasum -a 256 -c SHA256SUMS)
mkdir "$out"
install -d "$out/apex/com.android.runtime/bin" "$out/apex/com.android.runtime/lib64/bionic"
install -d "$out/system/lib64" "$out/vendor/lib64" "$out/proc"
install -m 755 "$runtime/runtime-apex/linker64" "$out/apex/com.android.runtime/bin/linker64"
for name in libc.so libm.so libdl.so; do
    install -m 644 "$runtime/runtime-apex/lib64/bionic/$name" "$out/apex/com.android.runtime/lib64/bionic/$name"
done
install -m 644 "$runtime/system-cxx" "$out/system/lib64/libc++.so"
install -m 644 "$mnl" "$out/vendor/lib64/libmnl.so"
install -m 755 "$helpers/mnl-isolate" "$out/launcher"
install -m 755 "$helpers/mnl-load-probe" "$out/probe"
install -m 644 "$helpers/BUILD-MANIFEST" "$out/BUILD-MANIFEST"
(
    cd "$out"
    shasum -a 256 launcher probe apex/com.android.runtime/bin/linker64 \
        apex/com.android.runtime/lib64/bionic/libc.so apex/com.android.runtime/lib64/bionic/libm.so \
        apex/com.android.runtime/lib64/bionic/libdl.so system/lib64/libc++.so vendor/lib64/libmnl.so \
        BUILD-MANIFEST > SHA256SUMS
)
echo 'Pinned load-only root prepared; no vendor code executed or hardware accessed'
