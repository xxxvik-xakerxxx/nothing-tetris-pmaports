# Native receiver inputs

Partial candidate, native CI pending. The seven receiver-policy files are
untouched. This is a pure native configuration path; it does not read mnld
globals, populate property receipts, initialize an engine or claim a fix.

Exact B4.1 private inputs from the outer workspace's
`worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41`:

- mnld SHA256 `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`
- libmnl SHA256 `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`

## Writer and startup audit

| Input | Initial value and exact writers |
| --- | --- |
| log byte88e40 | File-backed10. 78964 ORs the requested byte (argument saved at7890c);78a1c ORs11 (32-bit11111111 truncated);78acc clears bit0;78cdc ORs20. These are mutex-protected logging helpers. |
| byte de3c0 | ELF BSS zero. Startup57c88 calls60ac0. 60afc explicitly zeros it, then60b90 publishes0/1 only after XML GET of literal2309d **MPVT_LOG_ENABLE**, config byte1 and first setting double exactly0/1. Missing/disabled/other settings retain zero. This is MPVT logging, not gpsdl1 selection. |
| host word884c4 | File-backed zero. No nonzero resolved direct writer or relocation exposing this address. The candidate store63bf8 is a conditional clear; its base is path-dependent. Do not treat that conditional branch as a reachable host default. |

The executable-segment store census resolves address constructors, register
copies and relative GOT aliases, including wide/paired overlaps. It identifies
the seven store sites above and relative aliases86628->de3c0,86630->88e40.
This is static evidence, not a proof against arbitrary runtime pointer writes.

Stock logging is not just the initial10: startup6365c..6368c tests actual
`silentGnssLogging`, reads requested flags88bc0 and calls78900 or78a70.
Startup78608 reads `vendor.gpsdbglog.enable` and calls789c0/78a70;
63224/6325c can enable bit5. Runtime command handlers also call these helpers.
Their filesystem/property/debug requests are deliberately absent in native
quiet mode; this builder does not claim to reproduce their current values.

**Path correction:**62e54 makes x25=de000. If88c78 is nonzero,62fec does not
take the host branch and6301c bypasses63028: [x25+4c4] remains **de4c4**.
Only the host branch63020/63028 makes x25=88000 and uses **884c4**. Later
63a20 preserves x25 in x24 for the AP-config branch. The previous receiver
policy's884c4 naming is therefore host-only. Its files were not changed.

## Supported native choice

`b41_receiver_inputs_build(B41_RECEIVER_NATIVE_NMEA_QUIET, first, base, out)`
consumes an explicit native configuration choice and existing source-tagged
HOST first+68, primary receiver-fd bytes and resolved `UseCallback` path.
It emits log10, MPVT0, host AP-selector0 and second+c8 word0. Word0 reuses
the existing pure build-policy mapping; its `user`/`0` literals are ABI mapping
inputs, not properties claimed to exist. No property service is linked.

This intentionally overrides prior diagnostic policy in the *new config*,
including resolved log/debug bytes. It is not a stock-global mirror or an
active-library mutation. It changes exactly five bytes: second+4 and+c8..cb.
Only BUILD_POLICY is fulfilled; unrelated bytes, paths, fds, unknown mask bits
and receiver/stop/MPE gates survive. In particular MPVT0 never erases gpsdl1.

Log10 is deliberate, not blanket zero: lib52bfd8 skips file-control event
creation,52c05c skips the corresponding thread route,52c7c0 skips its cleanup
when bit4 is set. Bits0..3 clear avoid diagnostic files/dumps/serial output;
52bacc skips opening second+1ea when bit3 is clear. `UseCallback` is independently
selected at52ba40. The existing output owner still must own the real app/raw
sinks; their path is not replaced by an Android GPS_HOST log directory.

Offload is refused. HOST is a configuration choice, not a claim that SCP
offload exists or that firmware works. Existing native preparation separately
checks actual mapped offload state, fd identity/transfer and output ownership.
Other config producers and the real AGPS receiver still block complete INIT.

## Validation and parent CI

Run the static test against PINNED_MNLD PINNED_LIBMNL with
`PYTHONDONTWRITEBYTECODE=1` and
`PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012`.
No native compilation, emulation, hardware, SSH, CI dispatch or push occurred.
The C fixture covers1024 explicit quiet overrides, rejection/aliasing, fd0,
gpsdl1 preservation and unchanged gates; execution remains pending.

```sh
CI=true sh patches/gnss-navigation-audit/run_receiver_inputs_ci.sh
CI=true BIONIC_CC=/tmp/android-ndk-r27d/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang \
  sh patches/gnss-navigation-audit/run_receiver_inputs_ci.sh \
  --bionic-compile out/b41-receiver-inputs-test
```

Parent can apply `out.second` before startup_bundle_build. Do not manufacture
a `b41_receiver_property_owner` or route native configuration through collect.
