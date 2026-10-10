# XML/ADC sidecar CI closure

This bundle calls only our constructors/ownership code. Native tests read pinned
vendor ELF bytes as data and use synthetic mapped globals, memfd samples and
pipes. No vendor ELF execution, INIT, modem property emulation or hardware access.
No published source/header, shared workflow or main CI edits are required here.

## Minimum runnable staging

Place these12 files in the same audit directory:

```text
b41_xml_config.c              (published, unchanged)
b41_xml_config.h              (published, unchanged)
b41_xml_globals.c
b41_xml_globals.h
b41_slot0_adc.c
b41_slot0_adc.h
test_b41_xml_globals.c
test_b41_slot0_adc.c
test_b41_xml_adc_static.py
run_xml_globals_ci.sh
run_slot0_adc_ci.sh
run_xml_adc_ci.sh
```

The previous9-file freeze lacked the published decoder C/H and build runners;
its two docs are not compilation dependencies. `test_b41_xml_adc_runner.py` is
an additional offline admission/shell-syntax test, not a native build dependency.
Neither library association nor any host/worker/CLI C file is linked.

Inputs: exact independently pinned B4.1 libmnl.so, MNL_Config.xml and mnld
from the existing selected stock artifact. Pass their absolute paths; mnld is
needed only for static producer checks. No vendor download occurs in this runner.

```text
libmnl.so      3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90
MNL_Config.xml 7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31
mnld           285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83
```

## Single entrypoint

Linux CI dependencies: 64-bit C compiler, GNU timeout/coreutils, pkg-config,
native libxml2/OpenSSL development packages, pthread/libm, Python3+pyelftools.
ASAN/UBSAN/assertions remain enabled for native executable fixtures. No Unicorn
or Capstone dependency in the aggregate runner; binary emulation is separate.

```sh
CI=true sh "$AUDIT/run_xml_adc_ci.sh" native "$LIB" "$XML" "$MNLD" "$NEW_OUT"
```

Native runs16 feature/profile executions (each includes the full-stock tests)
plus the ADC fixture; retains binaries and per-feature value/mask outputs.
Compiler deadlines120s, fixture deadlines20s, static deadline30s, kill grace2s.
Failed output is retained; the completion manifest is written only after success.
No rerun into an existing directory. Parent workflow must bound the whole step.

For Bionic API28 builds, set `B41_BIONIC_CC` to the absolute pinned r27d NDK
`aarch64-linux-android28-clang`, and `B41_BIONIC_DEPS` to a genuine target-built
ARM64/API28-or-earlier dependency prefix containing:

```text
include/openssl/{evp.h,opensslconf.h,...}
include/libxml2/libxml/{parser.h,xmlversion.h,...}
lib/libcrypto.so
lib/libxml2.so
lib/...                      (real transitive target dependencies if needed)
```

CI owns version/source/build pins for these external dependencies. NDK import
stubs, host include directories/libraries, or generated successful EVP/XML mocks
are not substitutes. Runner checks actual AArch64 shared-library shape and
defined EVP_Digest/xmlReadMemory exports, then requires complete no-undefined
fixture linkage. These checks do not independently authenticate headers or ABI.
The new [real dependency workflow](BIONIC_XML_DEPS.md) builds pinned official
libxml2/OpenSSL sources with that same NDK/API28 compiler and then links these
fixtures. Its first run is pending; an arbitrary development prefix or host
library is still not a substitute for successful target build evidence.

```sh
CI=true B41_BIONIC_CC="$NDK_CC" B41_BIONIC_DEPS="$TARGET_DEPS" \
  sh "$AUDIT/run_xml_adc_ci.sh" all "$LIB" "$XML" "$MNLD" "$NEW_OUT"
```

`bionic` selects only cross-build plus static checks; `all` includes native tests.
Bionic executables are never run here, are checked as AArch64, and may not depend
on libmnl/libmipc. Cross-builds do not claim ARM execution or sanitizers on Android.
Artifacts include source/asset/binary hashes and dependency-library hashes.

Offline validation, safe outside CI and with no compiler execution:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_xml_adc_runner.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_xml_adc_static.py" "$LIB" "$XML" "$MNLD"
```

Optional source-oracle stage remains Linux-only and independent of this runner:
`test_b41_xml_set_consumers.py LIB XML NEW_OUT/native-xml/test_xml_globals` needs
pyelftools+Unicorn and published test_b41_startup.py/test_b41_xml_producer.py.
`test_b41_slot0_adc_producer.py MNLD` needs pyelftools+Unicorn and
test_b41_startup.py. They are not hidden native fixture dependencies. No local
Mac emulator retry. No assertions or sanitizer checks disabled.

## Backend gates retained

XML receipt covers only15 enabled features' global bytes. Actual reader-policy
bit/ordering, SET serialization/category5 output/log tail and first-config XML
policy remain unimplemented. Unknown actual mapped DCB chip fails, no fallback.
ADC transport accepts an immutable snapshot but does not establish its firmware
producer or the separate OEM diagnostic endpoint. Actual slot0 RTC/FM/control,
restart/internal RX stop and engine-wide configuration/transport dependencies
remain separate. This does not clear native init or navigation gates.

Native ASan/UBSan execution passed
[CI 38052531292](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38052531292)
at `0d7458d`: all16 XML feature/profile executions and the ADC fixture, using
genuine host libxml2/OpenSSL and independently pinned stock bytes. Downloaded
source/asset/binary manifests and the actual step result confirm native scope.
No Bionic fixture or vendor engine was executed by this job.

Next gate: genuine Bionic dependency build/link, then reviewed real
loader/global ordering and backend ownership.
Published43b4a2d ARM LOAD_OK remains load-only evidence, not engine INIT or fix.
