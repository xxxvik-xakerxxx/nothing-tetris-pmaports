#!/bin/sh
# Native fixtures execute our code only; Bionic fixtures are build-only.
set -eu
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
if [ "${CI:-}" != true ]; then
    echo 'XML/ADC native and Bionic compilation is CI-only.' >&2
    exit 2
fi
if [ "$#" -ne 5 ]; then
    echo 'usage: run_xml_adc_ci.sh native|bionic|all libmnl.so MNL_Config.xml mnld NEW_OUT' >&2
    exit 2
fi
mode=$1; lib=$2; xml=$3; mnld=$4; out=$5
case "$mode" in native|bionic|all) ;; *) echo 'Unknown build mode.' >&2; exit 2 ;; esac
for path in "$lib" "$xml" "$mnld" "$out"; do
    case "$path" in /*) ;; *) echo 'Require absolute input/output paths.' >&2; exit 2 ;; esac
done
test ! -e "$out" || { echo 'Output directory must be new.' >&2; exit 2; }
test "$(uname -s)" = Linux || { echo 'Linux CI required.' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python=${PYTHON:-python3}
for file in b41_xml_config.c b41_xml_config.h b41_xml_globals.c b41_xml_globals.h \
    b41_slot0_adc.c b41_slot0_adc.h test_b41_xml_globals.c test_b41_slot0_adc.c \
    test_b41_xml_adc_static.py run_xml_globals_ci.sh run_slot0_adc_ci.sh; do
    test -f "$here/$file" || { echo "Missing staging dependency: $file" >&2; exit 2; }
done
# Pin and static checks precede every compiler invocation; no emulator/vendor calls.
timeout --signal=TERM --kill-after=2 30 "$python" "$here/test_b41_xml_adc_static.py" "$lib" "$xml" "$mnld"
if [ "$mode" != bionic ]; then
    command -v "${CC:-cc}" >/dev/null
    pkg-config --exists libxml-2.0 libcrypto
fi
if [ "$mode" != native ]; then
    compiler=${B41_BIONIC_CC:?absolute NDK aarch64-linux-android28-clang required}
    deps=${B41_BIONIC_DEPS:?absolute genuine ARM64 Bionic libxml2/OpenSSL development prefix required}
    case "$compiler" in /*/aarch64-linux-android28-clang) ;; *) echo 'Require API28 ARM64 NDK compiler.' >&2; exit 2 ;; esac
    case "$deps" in /*) ;; *) echo 'Require absolute Bionic dependency prefix.' >&2; exit 2 ;; esac
    test -x "$compiler"
    readelf=$(dirname -- "$compiler")/llvm-readelf
    test -x "$readelf"
    for file in include/openssl/evp.h include/openssl/opensslconf.h \
        include/libxml2/libxml/parser.h include/libxml2/libxml/xmlversion.h \
        lib/libcrypto.so lib/libxml2.so; do
        test -f "$deps/$file" || { echo "Missing real Bionic dependency: $file" >&2; exit 2; }
    done
    # Header/package provenance is supplied by CI, not inferred from these checks.
    for library in "$deps/lib/libcrypto.so" "$deps/lib/libxml2.so"; do
        "$readelf" -h "$library" | grep -q 'Machine:.*AArch64'
        "$readelf" -h "$library" | grep -q 'Type:.*DYN'
    done
    "$readelf" --dyn-syms "$deps/lib/libcrypto.so" | grep -E 'GLOBAL.*DEFAULT.*[[:space:]]EVP_Digest(@|$)' | grep -qv ' UND '
    "$readelf" --dyn-syms "$deps/lib/libxml2.so" | grep -E 'GLOBAL.*DEFAULT.*[[:space:]]xmlReadMemory(@|$)' | grep -qv ' UND '
fi
mkdir -p "$out"
if [ "$mode" != bionic ]; then
    export ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
    sh "$here/run_xml_globals_ci.sh" "$lib" "$xml" "$out/native-xml"
    sh "$here/run_slot0_adc_ci.sh" "$out/native-adc"
fi
if [ "$mode" != native ]; then
    mkdir "$out/bionic"
    timeout --signal=TERM --kill-after=2 120 "$compiler" -std=c11 -O2 -Wall -Wextra -Werror -fPIE -pie -pthread \
        "$here/b41_slot0_adc.c" "$here/test_b41_slot0_adc.c" \
        -Wl,--no-undefined -o "$out/bionic/test_slot0_adc"
    timeout --signal=TERM --kill-after=2 120 "$compiler" -std=c11 -O2 -Wall -Wextra -Werror -fPIE -pie \
        -I"$deps/include" -I"$deps/include/libxml2" \
        "$here/b41_xml_config.c" "$here/b41_xml_globals.c" "$here/test_b41_xml_globals.c" \
        "$deps/lib/libxml2.so" "$deps/lib/libcrypto.so" -lm \
        -Wl,--no-undefined -Wl,-rpath-link,"$deps/lib" -o "$out/bionic/test_xml_globals"
    for binary in "$out/bionic/test_slot0_adc" "$out/bionic/test_xml_globals"; do
        "$readelf" -h "$binary" | grep -q 'Machine:.*AArch64'
        "$readelf" -d "$binary" > "$binary.DYNAMIC"
        if grep -Eiq 'NEEDED.*(libmnl|libmipc)' "$binary.DYNAMIC"; then
            echo 'Standalone fixtures must not depend on the vendor engine.' >&2; exit 1
        fi
    done
    sha256sum "$deps/lib/libxml2.so" "$deps/lib/libcrypto.so" > "$out/BIONIC-DEPENDENCY-SHA256SUMS"
fi
(cd "$here" && sha256sum b41_xml_config.c b41_xml_config.h b41_xml_globals.c b41_xml_globals.h \
    b41_slot0_adc.c b41_slot0_adc.h test_b41_xml_globals.c test_b41_slot0_adc.c \
    test_b41_xml_adc_static.py run_xml_globals_ci.sh run_slot0_adc_ci.sh run_xml_adc_ci.sh) > "$out/SOURCE-SHA256SUMS"
sha256sum "$lib" "$xml" "$mnld" > "$out/ASSET-SHA256SUMS"
find "$out" -type f -name 'test_*' -exec sha256sum {} \; > "$out/FIXTURE-SHA256SUMS"
printf 'mode=%s\nnative=asan-ubsan-if-selected\nbionic=api28-build-only-if-selected\nengine=not-called\n' "$mode" > "$out/BUILD-MANIFEST"
echo 'PASS: selected XML/ADC fixture stages; no vendor INIT or hardware.'
