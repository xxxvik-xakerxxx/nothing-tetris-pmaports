# Versioned MIPC Init Resources

Frozen candidate: b41_mipc_version_closure.py, b41_mipc_init_resources.py,
test_b41_mipc_init_resources.py and this document. Existing frozen production,
audit modules, shared CI and extraction scripts are unchanged. No integration
patch, native compilation, Mac emulation, phone action or library loading.

## Actual Closure Result

Four vendor libraries were read from
/private/tmp/tetris-b41-mipc-closure-ci38030808388/vendor/lib64:

| Library | SHA256 |
| --- | --- |
| libmipc.so | aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56 |
| libmtkrillog.so | aa057f4d00d1968c93eee3accb30866175d01297ebfdda81dcba8e40b4d342d6 |
| libtrm.so | 0cc93d3c3a8b9343bcc45ee1ea37dafd1b6b04c7e7d4bf1921fec5140385da68 |
| libmtkproperty.so | 74c68447636c4676bac8054f337111d75d946441a233c06f539985fec4fe3f01 |

Existing Bionic root: /private/tmp/tetris-gnss-root-ci37898372984.
BUILD-MANIFEST identifies commit2adc9cd94e7bcb6801b943990666fccf301ee1bd,
NDKr27d and mode=load-only-no-device-network. PLATFORM constants match that
root's actual SHA256SUMS, not guessed sonames or host-libc replacements:

- apex/com.android.runtime/bin/linker64 (SONAME ld-android.so)
- apex/com.android.runtime/lib64/bionic/libc.so
- apex/com.android.runtime/lib64/bionic/libm.so
- apex/com.android.runtime/lib64/bionic/libdl.so
- system/lib64/libc++.so

All nine provider files are retained by opened read-only descriptors after
whole-file hash checks. Decode hashes and parses the same immutable bytes.
The audit resolves294 symbol bindings. Missing library: liblog.so. The only
unresolved strong imports are libmtkrillog's __android_log_buf_write and
__android_log_assert, both requesting version LIBLOG from liblog.so. libc's
unresolved weak __scudo_default_options is reported but is not a loader failure.

Extract matching liblog from the already cached stock images if available:
vendor/lib64/liblog.so and system/lib64/liblog.so are discovery paths, not proven
locations. Record actual path and SHA in the existing manifest. A legitimate
existing platform liblog may instead be supplied with its independent pin.
Never create success-only log/assert/property substitutes. Additional provider
inspection uses an explicit FILE/SHA256 pair; duplicate SONAMEs reject.

## Version Checks

The resolver checks .gnu.version, .gnu.version_r and .gnu.version_d, matching
required version name/hash and declared provider, callable/data symbol type,
visibility and default-versus-hidden versions. VER_NDX_GLOBAL index1 remains
unversioned even when a base VERDEF names the SONAME. Bionic's legitimate GNU
IFUNC (type10, pyelftools STT_LOOS) satisfies function imports; no resolver code
is executed. Base-index and IFUNC handling avoid fabricated libc/loader failures.

The runtime dlopen("libtrm.so") in mipc_init also requires six dlsym exports:
libtrm_init, libtrm_deinit, libtrm_reset, libtrm_power_off_md,
libtrm_power_on_md and libtrm_md_event_register. All exist in the actual pinned
libtrm. These are checked separately from ordinary undefined ELF symbols.
Matching versions/types is static ELF evidence, not a proven C prototype,
runtime namespace, property service, modem handshake, calibration or GNSS fix.

## Owned Resource Adapter

inspect_resources(vendor_lib64, bionic_root, additional) is audit-only and can
report incomplete closure. acquire(...) always calls require_closure: there is
no caller boolean for bypassing that check. A successful acquire retains actual
provider descriptors/identities and decoded version bindings until close/context
exit. Current acquire correctly fails ENODATA for the missing liblog and closes
all nine descriptors; it cannot yield an authorized init lease from this bundle.

Provider acquisition rejects nonregular/symlink/FIFO paths before opening, uses
O_NOFOLLOW/O_NONBLOCK/O_CLOEXEC, detects path replacement and changes during
hashing, rejects duplicate SONAME and bad SHA, and revalidates retained file
identity before handoff. Parent must consume the owned descriptors/same immutable
staging, not silently reopen unrelated mutable paths. A lease is not dlopen,
native initialization, or permission to clear FIRST/SECOND/AGPS/STOP gates.

Once liblog is present, parent can acquire this actual resource lease and retain
it across its legitimate supervised Bionic-child loader handoff. Continue to
require runtime library association and sole transport ownership. No automatic
namespace, property, GPIO, modem or engine operations are introduced here.

## First Actual Init Boundary

Pinned mipc_init fba0 calls FINDCOM/OPENCOM atfbd4/fbd8 before allocating its
process-global state. It then starts a detached RX thread atfde0 and performs
message0x305/argument0xff handshake atfde8..ff20. On failure it repeatedly sets
a100ms per-call wait and retries until success (fec8..ff08), with no proven
overall retry bound. Therefore the parent's absolute deadline/kill/reap must
cover mipc_init itself, not just calibration141. Do not rely on its10000ms
timeout setting to bound the whole initializer.

After handshake it sends registration0x301, tags0x100=u32 value2,
0x101=terminated client name and0x102=one byte1. These internal transactions
precede calibration141. libtrm/property/CCCI resources are real prerequisites;
no forced property defaults or alternative ML4A fallback are provided.
Vendor parser bounds gap and lack of RX join remain as documented in the frozen
MIPC_B41_CLOSURE_CONTRACT.md. No unload/reinit/replacement before actual child
exit; no false successful calibration or engine run claim.

## CI Integration

Python only: pyelftools; no Unicorn, Capstone, native build or network required.

```
PYTHONDONTWRITEBYTECODE=1 python b41_mipc_init_resources.py \
  --vendor-lib64 "$VENDOR_LIB64" --bionic-root "$BIONIC_ROOT" \
  --provider "$LIBLOG" "$LIBLOG_MANIFEST_SHA"
PYTHONDONTWRITEBYTECODE=1 TETRIS_B41_MIPC_VENDOR="$VENDOR_LIB64" \
  TETRIS_BIONIC_ROOT="$BIONIC_ROOT" python test_b41_mipc_init_resources.py
```

Without LIBLOG, omit --provider; audit returns2 (expected incomplete closure).
Do not suppress this exit in a required loader gate. Tests intentionally assert
the current missing-liblog boundary while testing real asset descriptor cleanup;
give both environment paths to avoid four asset-test skips. All seven tests
passed locally using actual downloaded files. NativeMac SIGILL is not involved:
neither module imports Unicorn or executes a native library. Parent owns shared
CI and any subsequent native/Bionic initializer integration.
