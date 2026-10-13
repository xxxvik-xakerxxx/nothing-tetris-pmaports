# Native B4.1 L1/MVCD Nominal26MHz Owner

Status: **source-validated native path; compilation and live execution pending**.
Only these six files are owned: selectors.c/h, test_selectors.c,
test_selectors_source.py, run-ci.sh and this README. The CLI is compiled from
selectors.c with B41_NATIVE_L1_RUNNER. No workflow, package, shared download
controller, prior research or handset files are changed here.

## Native Ownership, Not OEM FINAL Observation

The standalone owner intentionally chooses its software policy. It does not
need to recreate a running MNL engine, observe FINAL globals, enable a secondary
transport, or acquire private records merely because the OEM caller stored
configuration in those locations. b41_bootstrap_observe remains an optional
OEM comparison API; it is not called by any native entrypoint.

The native policy is primary L1/MVCD, navigation mode3, secondary disabled,
nominal physical26MHz. The native path retains FE/COTMS in payload60, but calls
the pure clock synthesis at the acquired physical frequency. It never invokes
the OEM private frequency/adjustment decoder, changes FE to evade its gate,
constructs checksum-invalid records, or claims to reproduce private calibration.
The existing OEM bootstrap-field helper remains unchanged and still rejects FE
without its real private records. This distinction is tested in the CI fixture.

The immutable bootstrap grammar accepts an explicit effective frequency. Its
26MHz reference table row is public static policy, not per-handset calibration.
Source-backed grammar compatibility is not evidence that a real DSP accepted
the packet or that uncorrected nominal frequency will achieve a navigation fix.

## Actual Identity And Minimal Selection

b41_native_l1_identity_select takes the actual numeric conninfra chip and GPS
ADIE results. It copies only necessary immutable policy fields from the three
identified B4.1 records, without loading libMNL or fabricating a complete context:

| Hardware chip | GPS ADIE | Configured chip | Capability | Table profile | OEM navigation base |
| --- | --- | --- | --- | --- | --- |
| 6878 | 6631 | FFFF6878 | 370 | 5 | 6 |
| 6878 | 6637 | FFFF6878 | 370 | 5 | 10 |
| 6878 | 6686 | FFFF6878 | 370 | 5 | 10 |

IDs and capability are hexadecimal. The compiled values are source-specific
policy keyed by actual identity, not data copied from the current handset.
Unknown chip/ADIE is refused. The revision-independent matcher is deliberate:
51b3b0..51b3c4 skips revision filtering and 51b414 accepts that branch.
It is not evidence that disabled GPS hardware-revision ioctls returned0.
The runner makes no ioctl6/7/8 calls.

mnld's pointer pair887a0 relocates to de230/de2f0; capability_v2 copies the
selected record to the latter. Thus capability+14 produces configured de304
and capability+18 produces de308. Neither is an ADIE substitution.
The 50-entry profile table6ee1a8 selects profile5 for configured FFFF6878.

The native owner deliberately selects mode3 rather than inheriting the OEM
navigation base. 5ccc88..5ccc90 produces mode3/setting5/flags1 without secondary
state. The source-derived initial clock selector is0. Profile>=5 then installs
setting27 and emits profile7 in bootstrap. Secure default is the B3 predicate
(capabilities &0x0ffffff0)>30F; this produces1 for capability370. DSP selector0
selects metadata ioctl23 and integer fragment ioctl25. These are owned software
selections, not readiness or security-success certificates.

## Callable Path

1. b41_native_l1_identity_select(actual_chip, actual_gps_adie, &identity).
2. b41_native_l1_nominal_build(&identity, &first, actual_ioctl11,
   actual_ioctl30, &policy). It requires known frequency/profile/baud/FE/LNA
   bytes only; unrelated unresolved first-context or XML bytes do not block it.
3. Retain one session with fields=&policy.inputs and selectors=policy.selectors.
4. b41_native_l1_download_linux_begin(&owner, &policy, &session, deadline).
   This performs exactly one real ioctl23, preserves the complete20-byte ABI,
   checks the same session/fd and assembles the private116-byte frame using
   native resolved fields. No OEM private-record helper or MNL observation runs.
5. Continue the existing b41_download_linux_step until failure or
   ACKS_COMPLETE. Existing sequence matching, whole DMA reads, partial-write
   accounting, integer ioctl25 submission, deadline and first-fault behavior
   remain in the shared controller. Begin cannot restart an attempted owner.

The native payload/frame APIs are also exposed for a transport owner that
already acquired real ioctl23 metadata. Negative syscall status propagates;
positive OEM status18/2, another session, wrong command, short metadata, malformed
words and excessive fragment counts are refused. Output/input overlap is refused
and temporary key-bearing storage is wiped. No key or boot metadata is logged.

## Standalone Runner

Usage of the CI-built artifact:

```sh
gnss-l1-nominal /path/to/APCFG/APRDEB/GPS 5000
```

No live invocation was performed here. The runner:

- Opens the runtime physical GPS file read-only, requires a regular54-byte
  file, and reads only byte0 and bytes24..33. It never reads calibration36..51
  or synthesizes a complete52-byte record. Nonempty selects NV; interval0
  becomes2000. Frequency, interval, mode and profile are public diagnostics.
- Opens /dev/conninfra_dev O_RDONLY. Request8004C200 returns chip; request
  8004C203 with integer argument2 returns GPS ADIE. Errors/unknown IDs fail.
- Opens /dev/gpsdl0 O_RDWR|O_NONBLOCK exactly once. Pinned device open enforces
  exclusivity with EBUSY. It never opens gps1, duplicates the fd, retries,
  resets, reopens, or executes vendor code.
- Queries real ioctl11 and strict ioctl30 on that same fd. Only33 and0 plus
  actual NV26MHz are supported. FE is retained; baud is source constant115200.
- Queries real ioctl16 and29 into initially zero outputs. The pinned driver
  disables16 and29 and returns-EFAULT without copying an output. Those exact
  failures retain source-initialized native wire zeros, explicitly logged as
  failed queries, not successful LNA/timesync/revision discovery. ioctl16
  success can supply its actual LNA value; unexpected failures fail closed.
  ioctl29 requires the pinned unsupported result and unchanged output.
- Queries metadata23 once, then sends one bootstrap and the source-selected
  fragment sequence through the bounded shared Linux adapter. ACK completion
  is reported separately from RAM_CODE_READY/WORKING/fix.
- Uses one absolute monotonic deadline from process start, plus a SIGALRM
  watchdog. SIGINT/TERM abort the attempt. No userspace watchdog can bound a
  kernel-uninterruptible stall; external recovery remains a lifecycle concern.
  Cleanup performs only normal close, preserves the first error and wipes
  private frame storage.

The source-zero LNA field is not a discovered physical GPIO. Its producer is
mnld62bcc (sp+94 initially0), ioctl16 at63454..6345c and copy6348c/63498 even
on its recorded failure. The native policy preserves that wire convention.
No calibration success or hardware pin ownership follows from it.

## Real Remaining Gates

The sole fd must be the real gpsdl0 link with strict packaged1005 clock-query
behavior, packaged1008 bounded RX and the reviewed nonblocking TX extension.
Descriptor flags/fstat do not certify those kernel contracts. Real ioctl23
must return legitimate current-session ATF metadata. Firmware availability,
SMC/ROM behavior, ACKs, fragment delivery, RAM_CODE_READY and FSM WORKING remain
real dependencies; there are no fabricated keys, metadata or success tokens.

Nominal26MHz intentionally omits OEM private override calibration. Hardware
acceptance, fix/time/accuracy, cold restart, suspend/resume and coexistence are
untested. The correction removes an unnecessary OEM FINAL-state prerequisite;
it does not turn software selection or ACK completion into hardware readiness.

## Evidence And CI

Pinned assets:
mnld SHA256285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83;
libmnl SHA2563b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90;
kernel modules object e96f60dc081ae3525ef43d4bcf0ee5ee97e53835.
Tests also pin complete producer/matcher slices, the26MHz reference table,
gps_each_device.c and conninfra_dev.c.
TETRIS_MODULES_TREE selects the exact Git source checkout in CI (the parent
job uses out/lna-kernel-source); otherwise the existing local sibling is used.
Both kernel files are read with git show on the exact pinned commit, allowing
the job's blob:none checkout to materialize those blobs lazily.

Local static test command:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 patches/gnss-navigation-audit/dsp-download/live-inputs/test_selectors_source.py \
  /private/tmp/tetris-b41-providers-ci38048111345/vendor/bin/mnld \
  /private/tmp/tetris-b41-providers-ci38048111345/vendor/lib64/mt6878/libmnl.so
```

21/21 static tests pass; Python AST, shell syntax and whitespace pass.
No local native compilation, emulation, DSO/firmware execution, device access,
commit, push or CI dispatch occurred.

The existing workflow already calls dsp-download/run-ci.sh, which now invokes
this six-file runner (parent-owned integration). Our run-ci.sh prepares host
ASan/UBSan fixtures and compiles the CLI branch for device-free --help and
argument rejection tests. Those CLI fixtures intercept open/ioctl and terminate
with status99 if any profile/device acquisition is attempted. Invalid argument
tests require status2, including extra help arguments and invalid timeouts.
Native fixtures cover nominal clock golden words, FE preservation without
private records, identity errors, partial first-input admission, real normalized
query failures, packet/checksum grammar, metadata limits and overlap, then a
mocked ioctl23 feeding the shared bootstrap ACK -> integer ioctl25 -> fragment
ACK controller. Repeated begin/failed-query attempts do not issue more queries.

A static AArch64 musl build target is available through that same CI entrypoint:

```sh
sh patches/gnss-navigation-audit/dsp-download/live-inputs/run-ci.sh \
  /path/to/aarch64-linux-musl-gcc out/gnss-l1-nominal
```

Alternatively the parent workflow can set GNSS_NATIVE_MUSL_CC and
GNSS_NATIVE_OUTPUT before its existing dsp-download/run-ci.sh invocation.
The build requires an AArch64 musl toolchain already provided by CI; it downloads
none. It accepts any AArch64 -dumpmachine result, including musl-gcc reporting
its underlying aarch64-linux-gnu target. It preprocesses the actual features.h
and rejects defined __GLIBC__ before building. ELF validation still requires
AArch64 machine, absent INTERP and absent NEEDED.
The parent owns provisioning that toolchain and publishing the artifact in the
existing workflow. Neither host native tests nor the musl target have run yet.

The direct cross-build source contract is:

```sh
audit=patches/gnss-navigation-audit
dsp="$audit/dsp-download"
"$AARCH64_MUSL_CC" -std=c11 -static -DB41_NATIVE_L1_RUNNER -O2 \
  -Wall -Wextra -Werror -Wconversion -Wshadow \
  -frounding-math -ffp-contract=off \
  "$audit/b41_capability_branch.c" "$dsp/live-inputs/selectors.c" \
  "$dsp/wire.c" "$dsp/clock.c" "$dsp/bootstrap_fields.c" \
  "$dsp/bootstrap.c" "$dsp/download.c" "$dsp/download_linux.c" \
  -lm -o out/gnss-l1-nominal
```

No platform_profile.c, first-config constructor, library loader, vendor DSO,
Android NDK, libxml2 or private calibration service is linked. The legacy
capability reader remains linked for the optional existing audit API, but the
CLI's native identity selector never calls it or loads an ELF image.
