# Retained Native GNSS Session

Future opt-in1010 draft. No default package activation, local native compilation,
phone/SSH access, firmware execution, reset, commit, push or CI dispatch here.
The candidate-image wrapper is frozen and is not extended to admit1010.

## Actual Boundary

Parent reports one real r188 attempt using the standalone ca947b9 artifact from
CI38403683556: actual chip6878/ADIE6631, ioctl11=33, ioctl30=0, real NV26MHz/profile0,
all matched download ACKs and exit0. Parent then observed RAM_OKAY -> WORK at
uptime6907.432832, after the runner's close at6907.416270. FUNC_OFF later changed
WORK -> OFF with is_err=1. These are parent-supplied live observations, not tests
repeated here. They prove neither a navigation fix nor clean lifecycle.
No further hardware session is authorized before cold recovery.

The pinned FSM marks FUNC_OFF normal only from RESET_DONE or HW_STOP_MODE.
Closing from WORK always warns; waiting for ACK completion or adding an arbitrary
sleep cannot certify a safe close. Existing ioctl12 is TRIGGER_ASSERT and is
forbidden. ioctl13 reports link/reset status, not DSP WORK.

## Read-Only Producer

1010 adds plain integer ioctl31 with a fixed32-byte version1 ABI. It returns
the real open device's link ID, session ID, link state and READ_ONCE DSP state.
Link/session reads use their existing spinlock. DSP samples before/after detect
observed transitions and return EAGAIN; there is no lock shared across DSP/link,
so matching samples do not prove atomicity or exclude ABA/reset races.

The ioctl checks actual dev/is_open, validates its index and link object, zeroes
only ABI reserved bytes, and performs one fixed copy_to_user. It never consumes
caller input or changes firmware, memory-mapped hardware, FSM, reset, power,
DMA or waitables. Existing ioctl12/13 and old gpsdl_v051.h remain unchanged.
A separate READ_ONCE getter leaves the existing FSM getter/behavior unchanged.

ABI fields are eight32-bit words, no pointers or secrets; native and compat share
the same layout. The shared header uses kernel __u32 or userspace uint32_t, avoiding
glibc/Linux-header fallback in the standalone musl build. Actual-state enum values
and source slices are pinned at e96f60dc081ae3525ef43d4bcf0ee5ee97e53835.

## Caller Contract

Link session.c into the existing standalone download owner. It borrows the sole
fresh O_RDWR/O_NONBLOCK gps0 fd; it never opens, duplicates, closes, resets or
resumes it. Snapshot queries verify its real character-device identity against
the actual /dev/gpsdl0 node before issuing ioctl31. State, inode/device identity,
session ID and a single CLOCK_MONOTONIC deadline remain tied to that lifetime.

```c
struct b41_native_session retained = {0};
status = b41_session_attach(&retained, gps_fd, deadline_ns);
/* Run the existing one-attempt download controller on this exact same fd.
 * Do not continue after failed metadata/TX/ACK or replace that first failure.
 */
while (!status && retained.stage == B41_SESSION_WAIT_WORK)
    status = b41_session_wait_step(&retained);
/* WORKING is an actual sampled kernel FSM state, not engine init or a fix.
 * Each event-loop call is scheduled within the existing absolute deadline.
 */
if (!status) status = b41_session_stop_begin(&retained); /* explicit FW action */
while (!status && retained.stage != B41_SESSION_STOPPED)
    status = b41_session_stop_step(&retained);
/* Only STOPPED admits the caller's normal close. On failure, retain the fd
 * and first error in a LIVE supervisor; never return/exit and call that
 * retention. Process exit implicitly closes its descriptors. Never reset/reopen.
 */
```

stop_begin re-queries actual same-session WORK before admission. Primary FE05/u16(4)
is the source-proven stop command (5328b0..c4,50bbe4,50bd60,554ae8), not PMTK161/0
or ioctl12. It queues accepted bytes once and preserves partial progress. EAGAIN
is pending capacity, not a second firmware attempt. Any other write failure latches.
The exact frame is aa f0 06 00 05 fe 04 00 0d 01 aa 0f; its escaped
header/payload/checksum region contains neither0xaa nor0xde. The AA framing bytes
remain literal. No secondary write or opaque DSO call occurs.

After the frame is accepted, the owner waits for real DSP RESET_DONE while the link
remains OPENED. It then invokes existing ioctl18/arg0 once: the existing normal
deep-stop route. It does not invoke this route from WORK, where the stock FSM may
warn/reject it. Success of ioctl18 alone is not a stop certificate: STOPPED requires
a subsequent real HW_STOP_MODE/SUSPENDED snapshot. There is no retry or recovery
reset. A first error remains terminal and subsequent calls issue no syscalls.

Stock ENTER_DPSTOP ignores the return from gps_dl_hal_link_power_ctrl before
changing the FSM and acknowledging suspend. Therefore STOPPED certifies only the
real sampled kernel STOP/SUSPENDED states and source-ordered requests, not physical
power/register acknowledgements or clean teardown. Retain this hardware gap; do
not promote it to a lifecycle PASS without the supervised cold stop/close checks.

The deadline is checked before/after operations. Existing ioctl18 kernel waits,
SMCs and close are not proven preemptible. Integrated callers need their existing
external recovery/watchdog owner; never report hard latency or teardown guarantees.

## Optional Tool

gnss-session inspects an inherited gps0 fd; its parent MUST retain the original
file reference. Default FD invocation is read-only snapshot. --wait-work only
queries. Explicit --stop waits for WORK and performs the stop sequence above.
This is not a download runner and does not acquire another gps0 open.
The integrated owner should link session.c directly, with no handoff/extra reader.
The child has a bounded alarm for a stalled syscall; parent-held fd/recovery
responsibility survives its exit. Kernel-uninterruptible stalls remain possible.

```sh
gnss-session 3
gnss-session 3 --wait-work 5000
gnss-session 3 --stop 5000
```

Only allowlisted sampled states/errors are printed. No metadata/key/calibration,
binary frame recorder, NMEA logger or parent CI secret output is introduced.
No legacy r188 ioctl31 fallback exists: EFAULT is a real unsupported-ABI failure.

## Navigation And Time

INIT is still a separate protocol/host-processing task, not an opaque FINAL snapshot
requirement. Static tests pin the actual post-init parameter42/subtype3 route to
FE05/subtype50 payload32 00 00 01 00. That is configuration, not a sufficient start.
The apparent param1 counterpart calls4fa5f8 and repeatedly sends FE05/arg4: a reset
path, not native start. Host initialization also contains FE1C/no payload and
FE05/arg41 at51e57c..b0 after several data-dependent host algorithm calls. These
immutable constants do not establish that sending them alone initializes GNSS.
They are therefore NOT emitted by this session owner.

Real UART AA F0 frames enter554d3c ->509830 and host processing; they are not NMEA
or a position struct. Output-ready at533674, get_position return0 at534c88 and
the getter's0xc60-byte buffer do not prove a fix. A native measurement/epoch decoder
and position validity schema remain actual implementation gaps; no guessed
lat/lon casting or caller-set success token is supplied. This module does not
consume RX, so the download/navigation parent remains the sole stream reader.

The earlier six-hour phone UTC offset is historical. Parent reports intentional
offline operation, manual host-epoch synchronization at13:59UTC already completed,
and correct14:38UTC readback. This is not a current clock failure or a request for
RTC/NTP changes. This module uses only MONOTONIC deadlines; the manual correction
does not alter them. It sets no clock, synthesizes no seed record and sends no time
seed. A future time-dependent native INIT still needs source-proven serialization
and retained acquisition/send timestamps plus explicit measurement uncertainty/age;
the corrected readback alone is not that packet contract. OEM private clock
calibration remains absent, not fabricated.

## Verification And Integration

Static only locally:

```sh
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 -B patches/gnss/native-session/run.py \
  --vendor ../android_kernel_modules_nothing_mt6878 \
  --libmnl /private/tmp/tetris-b41-providers-ci38048111345/vendor/lib64/mt6878/libmnl.so
```

In parent GitHub CI only, add --ci-native with clang and the retained pinned assets.
That builds actual-source snapshot fixtures, wrapped native controller fixtures,
and help/rejection tests. No fixture accesses a device. Tests cover same-session
WORK, no read-only writes, partial/EAGAIN TX without replay, exactly one HWSTOP
after real RST, actual STOP verification, state/ABI/fd/session changes, clocks,
deadlines, first-error retention and no close. Native fixtures have NOT run here.
Eighteen Python static/source tests cover deterministic stack/hash checks,
exact patch check/application, immutable stop/navigation/output slices and no RTC seed.

The integrated runner adds just patches/gnss/native-session/session.c to its existing
eight-source musl contract, includes session.h, and replaces ACK->close with the
caller contract above. `B41_NATIVE_L1_RETAINED_SESSION` selects this additive path
in the tracked selectors.c. It requires actual ON/RESET_DONE before MVCD and the
same descriptor/session/deadline through sampled WORK and stop. Any post-open
failure enters a live recovery-hold with no further firmware action, query or
close. SIGALRM/HUP/INT/TERM/PIPE interrupt the attempt rather than terminate its
owner. Forced termination or an uninterruptible kernel stall still needs external
cold recovery; no process can retain a descriptor after its own death.
`run_download_ci.sh` builds the integrated AArch64 musl artifact and device-free
main-loop fixtures for pending WORK, success/close ordering, attach/metadata/TX/
stop/session failures and interruption. The synthetic hold intercept exits only
its device-free test child; production keeps waiting. Native execution and the
new image/hardware lifecycle remain pending.
The optional tool has a separate two-source build (CI only):

```sh
musl-gcc -std=c11 -static -O2 -Wall -Wextra -Werror -Wconversion -Wshadow \
  patches/gnss/native-session/session.c patches/gnss/native-session/session-tool.c \
  -o out/gnss-session
```

Before any hardware use: full matching CI kernel plus connadp/conninfra/v051 module
build and strict real-export modpost with verified1001..1009 then opt-in1010.
Touched production units are linux/gps_each_device.c and hal/gps_dsp_fsm.c plus
their actual headers. Use the package's real compiler/config and recompile the
complete matching modules, not only the host fixture or two ARM64 objects.
No workflow, APKBUILD, frozen candidate composer or installed module was modified.
Next supervised test requires a new matched candidate image and cold recovery.
Normal stop/close, cold repeats, lifecycle and model portability remain unvalidated.
Exact parent-owned composition targets and the unresolved installed-module identity
are recorded in [CI-INTEGRATION.md](CI-INTEGRATION.md). The APIs and1010 patch are
frozen for that integration; no integrated runner is added here.
