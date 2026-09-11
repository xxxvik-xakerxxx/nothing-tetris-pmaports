# Current Port Status

Updated: 2026-09-11.

## Confirmed Display Work

The user confirmed visible native output and removal of redraw flicker after
the route correction and use of OVL frame-completion IRQ bit 1 rather than
frame-start bit 14. These are patches 0096 and 0097, originally committed as
3a490d386dd549e17201026dde4625bd262d9168 and
aecf4f44f4170952709a7dd514538f0d75b55e22 in hardware-integration.

CI 34492172863 produced the installed r153 / kernel #154 image. Hash-checked
super/userdata installation booted with native 1080x2400 DRM and no diagnostic
display module. U-Boot is 60bcf22fdc0a94526424db59fc7640298ea8f0dd. The installed
FIT SHA256 is da5e33c9342b1a7d4ea4af7b278496021b3d222ca5756dd1d7338058282602a2.
A 32 MiB USB regression transfer passed. An initial DPMS test failed at cycle
five; a separate readiness-aware test completed ten cycles, with 30 DRM
sequence steps per cycle and USB/SSH retained. Physical inspection following
that latter test is still pending. Do not erase the initial failure or count
DPMS as system suspend/resume.

Status: **Partial**, not universal or complete display support. Cold repeats,
full power lifecycle, alternate panels/SKUs, 120 Hz and accelerated rendering
remain unproven. The observed compositor uses software rendering.

## Main-Branch Promotion

The repository's primary branch is `main`, not `master`. A clean promotion
candidate starts at ee994e4236d69c9f3eb18e81614dd0dff9e60266 and carries the
display implementation from aecf4f4: panel patch 0050, patches 0056 through
0088, routing/IRQ patches 0096/0097, the framebuffer compatibility update,
native kernel configuration, native DTB/FIT selection and route tests.
Kernel revision 154 and device revision 10 identify this separate candidate;
it must not be confused with the installed full-integration r153 image.

Patch 0057 has a context-only rebase removing the unrelated MFG-controller
enum context line, so promotion does not require the experimental GPU power
inventory. Display runtime changes are otherwise copied from the recorded
integration revision. The candidate retains main's unrelated driver state;
it does not import the new modem/GNSS/camera/GPU compile experiments.

All 72 kernel patches apply in package order to the pinned upstream archive;
source/checksum validation and the route connect/disconnect model pass.
Promotion is pending CI and installation/lifecycle checks. It has not yet
been merged into main. Once gates pass, merge the
implementation and this record together; do not leave confirmed changes
only on a feature branch or mark a subsystem Works from command exit status.

## GSM And GPS

SIM detection, network registration, calls, SMS and mobile data are not
working yet. U-Boot diagnostic commit 38192f202c8bc3009efbb1d357b97975768424af
was published with explicit permission; CI 34575135682 passed. This is a
build result, not modem startup or a handset installation result.

In the separate GNSS worktree, a bounded primary-link BINFO exchange obtained
a checksum-valid FE31 index-zero acknowledgement on r153. Closing after that
incomplete download triggered the driver's off-done timeout and forced
A-die-off path. The phone was cleanly rebooted and USB/SSH recovered. A native
full-fragment candidate passes 29 substituted-I/O scenarios but has not run
on the handset: DSP readiness and shutdown ordering still need resolution.
No navigation fix, GPS coordinates or safe GNSS lifecycle is established.

Per-device NV/calibration data is not replaced or published. Extracted vendor
binaries and local register logs remain outside Git.
