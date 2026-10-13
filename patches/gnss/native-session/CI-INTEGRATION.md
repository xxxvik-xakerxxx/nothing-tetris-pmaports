# Native Session CI Contract

This is the parent integration contract, not a new workflow or image composer.
The candidate wrapper published at5da3c54 is frozen. Existing1009 and the
read-only1010 draft stay separate. No default activation or hardware test here.

## ABI And Platform

The old interface is plain-integer ioctl, including11/18/23/25/30. Preserve it;
do not translate it to `_IO*`, call assert12, enable disabled revision6/7/8 or
invent a query0. New31 copies eight32-bit words from the actual open session.
Its header name does not certify any installed module or kernel ABI.

At source pin e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, v050 and v051 both
link ../../linux, ../../hal and ../../link. Thus the new read-only producer is
common code, while the hardware backend is NOT interchangeable. Unmodified v050
has GPS_DL_GET_PLATFORM_CLOCK_FREQ=0, lacks ATF MVCD objects and its bootup-info
provider returns false. v051 supplies ATF MVCD and clock management. Current
APKBUILD and the existing full-module gate select plat/v051/gps_drv_dl_v051.ko.

Read-only inspection on r188 identified `/sys/module/gps_drv_dl_v051` and
`/lib/modules/6.18.0/extra/mediatek-connectivity/gps_drv_dl_v051.ko`, with vermagic
`6.18.0 SMP preempt mod_unload aarch64`. The historical "legacy v050 ABI" label
meant the integer calling convention, not a confirmed v050 hardware backend.
This matches the package's v051 module name, but does not establish new31 support
or the source identity of an arbitrary replacement module. No GNSS open was used.
Build the new module, kernel and suppliers together; do not substitute an old .ko.
Source tests retain both platform distinctions.

## Exact Targets

1. Static/source target, retaining the CI Git-object tree and pinned libmnl:

```sh
PYTHONPATH=out/capstone python3 -B patches/gnss/native-session/run.py \
  --vendor out/lna-kernel-source \
  --libmnl out/b41/vendor/lib64/mt6878/libmnl.so
```

2. Device-free native target in GitHub CI only: the same command with --ci-native
and CC=clang. run.py builds the actual-source producer harness, wrapped session
controller, and help/rejection fixtures with ASan/UBSan. It is NOT kernel modpost
or an artifact suitable for installation. Asset paths above are parent-selected
CI paths, not claims that a new job has already created them.

3. Full matching module target: extend the existing parent-owned
ci/kernel-object-smoke.py --gnss-tx-module sequence with a distinct opt-in
candidate-1009-1010 variant AFTER candidate-1009. The old target alone builds
only1001..1008 and1009; it does not include1010.

Use its prepare_gnss_tx_sources then apply_gnss_tx unchanged. Before applying1010,
compare every retained preimage with native-session/STAGING.json baseline_sha512;
the new UAPI path must be absent. Check all inputs and patch identity before any
source write. Apply the exact patch with git apply --check --whitespace=error,
then git apply --whitespace=error. Compare all four outputs byte-for-byte with
generate.transform(path, original), not only patch success. Preserve1009 TX,
existing UAPI, FSM behavior and all unrelated sources. Clean the GPS build before
compiling this third variant; do not label the earlier1009 module as1010.

Changed real units/headers, relative to the connectivity source root:

```text
gps/data_link/linux/gps_each_device.c
gps/data_link/hal/gps_dsp_fsm.c
gps/data_link/hal/inc/gps_dsp_fsm.h
gps/data_link/linux/inc/uapi/gpsdl_v051_session.h (new)
```

For the current package's v051 backend, actual Kbuild object targets are
linux/gps_each_device.o and hal/gps_dsp_fsm.o under gps/data_link/plat/v051.
The required final target is modules, producing gps_drv_dl_v051.ko, not just
these objects. Reuse gnss_connectivity_make and the real CONFIG_MTK_GPS_SUPPORT=y
plus KBUILD_EXTRA_SYMBOLS from the built connadp/conninfra tables. Build real
kernel vmlinux/modules exports, connadp, conninfra, then GPS in that order with
the package compiler/config and strict modpost. Do not fabricate symvers or use
KBUILD_MODPOST_WARN to bypass imports. Record compiler, config, full source/patch,
kernel, supplier exports and module hashes per variant.

4. Full-image target: opt-in1010 on a disposable copy AFTER the unchanged frozen
1009 composition, BEFORE checksums/retention append. Parent needs a separately
reviewed1010 extension and an explicitly reserved distinct package revision,
profile/report/artifact name; r188 must not be reused. Append1010 immediately after
1009 in BOTH source and vendor prepare order with zero fuzz and the actual
STAGING.json SHA512. Regenerate checksums without SKIP; prepare/build kernel,
all external modules, boot/FIT and rootfs together. Retain current loader,
reservations, config-off boundaries, supplier selection and identity evidence.
Do not extend or weaken either frozen composer to admit it automatically.

## Integrated Download Owner

The parent-owned tracked selectors.c runner adds only session.c to the existing
eight production sources. Include session.h; use the SAME sole fresh gpsdl0 fd
and absolute MONOTONIC deadline for attach, download, WORK wait and stop. Existing
real profile/identity/clock/metadata queries and one-attempt ACK controller stay.
The optional inherited-fd tool is not this integration.

Attach before MVCD, retain its actual session ID, run download on that fd, then
wait_step until sampled WORKING. Only explicit stop_begin/stop_step may write the
source-pinned FE05/u16(4). Wait actual RESET_DONE/OPENED, issue18/arg0 once, then
require actual HW_STOP/SUSPENDED before the caller's normal close. Query31 errors
on old modules are terminal unsupported-ABI failures, never fallback readiness.

Every failure after open, including attach/metadata/download/deadline/signal,
must preserve the first error and fd in a LIVE recovery owner. No return, exit,
default SIGALRM death, cleanup-close, reset or reopen may masquerade as fd
retention. If a worker exits, an already-live supervisor must retain that exact
file reference. Recovery holding makes the attempt terminal, not successful and
not another attempt; no later FW action is authorized by a timeout.

Required integrated CI fixtures include ACK-before-WORK, pending state queries,
same-session/fd changes, post-open metadata and download failures, signal/deadline
failure entering live hold, and stop failure with no close/retry. Success must
verify frame acceptance, real RST, exactly one18, actual STOP/SUSPENDED, then one
normal close. No fixture may access a device. These runner fixtures are parent
work; the current session fixtures do not prove integrated process-lifetime hold.

Stock ignores the HAL stop return: software STOP is not physical teardown proof.
Cold recovery and a full matching image precede any further GNSS open. Navigation
INIT/output semantics, normal close and hardware lifecycle remain unvalidated.
