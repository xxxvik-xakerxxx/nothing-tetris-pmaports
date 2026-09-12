# MT6878 native lifecycle candidates

These patches are not in APKBUILD and do not change the installed r153
image. Do not enable POSTMASK by adding only this helper patch to a build.

## POSTMASK boundary

The read-only r153 snapshot found EN=1, CFG=0x146, INTEN=0x917 and shadow=3
in the inherited POSTMASK block. The bounded live change of CFG bit 0 to
0x147 sustained 15 frame completions, but also produced one abnormal EOF
8278 us after the changed-phase first sample. Restoration returned clean
frame completions. This supports relay steady-state only, not live switching,
DMA quiescence, pixel correctness, cold initialization or stable lifecycle.

Candidate 0001 uses the existing native POSTMASK helpers. Only a future
mediatek,mt6878-disp-postmask node selects the new behavior:

- config disables local interrupts, establishes shadow bypass with a masked
  write, sets dimensions and selects the B4.1 no-round-corner relay value;
- stop masks local interrupts before disabling the block;
- other compatibles retain the existing generic behavior;
- no DMA address/length is written, and no IRQ handler is added.

Configuration must happen while the pipeline is stopped. The current r153
CRTC initialization interleaves config and start for each component, so
inserting POSTMASK after OVL does not itself establish that requirement.
Review a MT6878-scoped configure-all-before-start phase before activation.
Also review the DT resource, clock/power lifecycle, mutex membership, route
table split, binding and error rollback. Other inherited PQ blocks remain
outside native ownership; this is not the complete handoff solution.

## Checks

Run `sh patches/native-display/check-postmask.sh /path/to/prepared-linux`.
It applies the candidate without fuzz to a temporary copy, extracts the
actual changed config/start/stop functions and tests eight combinations:
MT6878/MT8192, two dimensions, and NULL/non-NULL command queue arguments.
It checks write order within config/stop, shadow-bit preservation, no engine
enable during config and untouched DMA address/length. A wrong generic
MT6878 configuration must fail. The command-queue writer is mocked; these
tests do not execute CMDQ, CRTC startup or hardware.

The changed translation unit also compiled with clang 21.1.8 / ARM64 against
the existing prepared 6.18 diagnostic tree. That is not a reconstructed full
r153 package build, full modpost or CI artifact. Exact APKBUILD-order apply,
target compilation and DT validation must be repeated for the eventual
combined activation candidate before CI. All source facts come from local
Linux and Nothing B4.1 ee2be53, not the older checked-out vendor branch.

## MT6878 callback ordering

Candidate 0002 separates config and start on MT6878 MMSYS0 only; all other
SoCs retain the interleaved order. It remains outside APKBUILD. It does not
add a POSTMASK node, change routing, or stop inherited hardware. Configuring
all native components before their start callbacks is necessary but not
sufficient proof that a bootloader-owned engine is actually stopped.

Run `sh patches/native-display/check-start-order.sh /path/to/linux-source`.
The runner requires the exact pinned base CRTC blob, reconstructs the CRTC
and local headers in APKBUILD patch order, applies candidate 0002 and
compiles the actual startup-loop body into a host trace harness. Twenty-four
cases cover MT6878 versus generic ordering, five/six components, DSC present
or absent and repeated invocation. A deliberately interleaved MT6878 mutant
must fail. This does not execute the mutex, clock/power error paths, CMDQ,
plane setup, kernel scheduling or hardware state transitions.

Setting START_ORDER_BUILD_DIR exports the reconstructed source and its local
headers for a short target object build. ARM64 clang 21.1.8 compilation of
mtk_crtc.o passed against the prepared diagnostic tree. The first attempt
failed because the external mtk_crtc.h included the unpatched external
mtk_ddp_comp.h before the local one; exporting mtk_crtc.h corrected header
selection without adding fake declarations or changing the patch. This is
not a complete kernel/link/DT/CI test or a live lifecycle result.

Raw phone evidence and remaining gates are in
`docs/DISPLAY_FIRST_FRAME_AUDIT.md`.

## POSTMASK topology

Candidate 0003 adds the MT6878 binding, DT node/alias, component match and
POSTMASK between the last OVL and DSC in the native path. It splits the
existing route across those two edges, retaining the proven d00=0x10001,
d30=0 and d60=0x20000 values. It also explicitly selects the inherited
DITHER path at e24 bit 0 and d20 bit 1. This is not native ownership of
DITHER or the remaining PQ chain. POSTMASK mutex membership already exists
in the packaged driver (bit 14).

Run `sh patches/native-display/check-topology.sh /path/to/linux-source`.
The runner reconstructs the relevant files in APKBUILD order, checks and
applies 0003, then compiles the actual before/after route tables and main
component arrays into a host test. It checks all path edges, component
order, mutex membership and 768 full register-array comparisons (256
initial states, three repeated connects). Only the two newly owned selector
bits may differ from the baseline. A mutant restoring the incorrect PQ
fan-out must fail. This models register writes, not hardware timing,
disconnect, CMDQ, DMA or power transitions.

The changed mtk_drm_drv.o also compiled for ARM64 with clang 21.1.8 against
the existing diagnostic tree and reconstructed CRTC/component headers.
The compiler differs from the original 21.1.2; this is not a complete
kernel/link/DT/schema/CI validation. The candidate remains outside APKBUILD.

Before activation, establish actual inherited-engine quiescence. Candidate
0002 only delays start callbacks: the mutex is enabled before configuration,
and a previously enabled POSTMASK can still be running. The B4.1 DT also
describes POSTMASK's memory path; a relay-only node omitting DMA resources
must not be taken as evidence that inherited memory transactions stopped.
No current test justifies a blind reset, live configuration toggle or
unconditional stop loop across the inherited PQ chain.
