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
Kernel revision 154 and device revision 11 identify this separate candidate;
it must not be confused with the installed full-integration r153 image.

Patch 0057 has a context-only rebase removing the unrelated MFG-controller
enum context line, so promotion does not require the experimental GPU power
inventory. Display runtime changes are otherwise copied from the recorded
integration revision. The candidate retains main's unrelated driver state;
it does not import the new modem/GNSS/camera/GPU compile experiments.

All 72 kernel patches apply in package order to the pinned upstream archive;
source/checksum validation and the route connect/disconnect model pass.
CI run 34575901650 for 8f61a02d2e0d12584a11a111998c1adf4e89b040 completed
successfully with kernel r154 / device 8-r10, as reported in the offline
handoff. Those images have not been installed. The audio/greeter follow-up
below is device 8-r11 and is not covered by that successful image build.
Promotion is pending a new artifact check and clean-install/lifecycle checks. It has not yet
been merged into main. Once gates pass, merge the
implementation and this record together; do not leave confirmed changes
only on a feature branch or mark a subsystem Works from command exit status.

## Scoped Audio/Greeter Follow-Up

Starting from clean display-main-promotion `7d10744`, the unpublished device
8-r11 candidate carries these installed integration fixes. The seven payload
files in `5f52b75` are copied byte-for-byte; the follow-up also restores the
package directory creation from `0b8c4164`:

- `384f155`: audio policy starts with the graphical session, excludes greetd,
  and creates the mono remap after UCM publishes the master sink. The early
  PulseAudio fragment only disables stream-device restoration.
- `980c566`: greetd's PulseAudio desktop autostart is hidden and client
  autospawn is disabled, leaving audio ownership to the login session.
- `bcd3d93`: capture controls are scoped to the UCM Mic device. Speaker and
  Earpiece sections remain unchanged; the imported validator enforces this.
- `8c1ccf4`: tmpfiles creates the greeter dconf directory with mode 0700 and
  greetd ownership to prevent the observed settings retry loop.
- `0b8c4164` (not `cb121c1`): package the dconf directory itself with mode
  0700 and numeric owner/group 113:113, as present in installed r153's
  `aecf4f4` source. This was missing from the initial `5f52b75` transfer.

The initial candidate's tmpfiles-only configuration was not equivalent to
the installed package contents. Before tmpfiles runs, the two mode-0644
PulseAudio files create root-owned, searchable parent directories, but do not
give greetd permission to create a missing dconf child inside `.config`.
Packaging the child removes that first-start dependency; the tmpfiles rule is
retained to restore its named ownership/mode on boot. No recursive chown of
the greeter home or its shared configuration is added.

The rootfs gate now checks the greetd passwd/group mapping (113:113, home
`/var/lib/greetd`), the actual dconf directory's 0700/113:113 metadata, and
search permission through each parent for that identity. Numeric IDs are the
preserved package contract, not inferred from the host account database.
A changed target account mapping must fail the gate before installation.
The device greetd drop-in only overrides rendering and ExecStart; it does not
explicitly order tmpfiles. The pinned Phosh drop-in also only overrides
ExecStart. The target base greetd/tmpfiles units were not available for this
offline audit, so no claim is made that their boot ordering was verified.
The packaged directory and preboot metadata gate avoid relying on that
unverified ordering. Candidate r11 still needs a clean boot proving no dconf
retry; r10 CI success and installed integration r153 are distinct evidence.

Device sources, SHA512 checksums, install paths and the package UCM check are
updated. Overlay checks and only the audio/greeter rootfs assertions in the
workflow follow the new ownership. No workflow was dispatched. Kernel APKBUILD,
configuration and every kernel patch remain identical to `7d10744`, including
the main-based native display series. GNSS remains the existing main v050
state: no v051, readonly helper, or unrelated hardware integration is imported.

Offline validation passed:

- `sh scripts/validate-pmaports-overlay.sh`, including all package checksums.
- Independent source/checksum coverage: all 37 device sources; seven selected
  payloads equal their source commits; six scoped mode-0644 install mappings
  and the package UCM check are present.
- UCM validator accepts the candidate and rejects the old global Mic scope
  and a modified Speaker section.
- Shell syntax and workflow YAML parsing pass. The scoped rootfs assertions
  accept local staged files and reject early remap, enabled greeter autostart,
  and a missing dconf rule. This does not execute target systemd or tmpfiles.
- The r11 directory follow-up executes the actual scoped APKBUILD install
  sequence in a disposable, network-disabled Alpine 3.23 container with the
  checkout mounted read-only. The artifact metadata gate passes and UID 113
  can write the dconf database path before tmpfiles. Wrong directory mode,
  owner, inaccessible parent and changed account mapping are rejected. These
  are synthetic package fixtures, not a target rootfs build or handset test.
- Kernel package, deviceinfo, initfs module list and GNSS payloads are unchanged;
  `git diff --check` passes. Full package build/check and CI were not run.

### Separate Initramfs USB Regression Gate

The installed integration source `aecf4f4` carries initramfs 3.12.3 and the
default-off stable-USB-identity patches plus their application helper. This
display branch has neither. Its `deviceinfo` and `modules-initfs` match
`aecf4f4`: NCM remains selected and no MAC seed is configured. Thus the source
comparison does not imply removal of an enabled stable-MAC feature; both
descriptions leave generated NCM addresses in use. It also does not establish
equivalent initramfs behavior or inspect the installed binary initramfs.

Keep that dependency difference explicit and outside this audio/greeter commit.
Before replacing installed r153, inspect exact candidate initramfs package
versions/content and check NCM module, gadget setup, USB identity and early
DHCP behavior. Then require a separately authorized clean CI installation with
recorded bootloader/kernel/DTB/rootfs hashes, rollback and one control session.
Verify USB enumeration, DHCP/SSH, reconnect and a hash-checked transfer before
audio tests; an SSH timeout alone is not evidence of kernel failure.

Require greeter startup without PulseAudio ownership or dconf retry, session
audio policy/preset activation, speaker and earpiece playback, and Mic capture
enable/disable without changing playback controls. Repeat cold starts, warm
reboot and lifecycle regression with USB retained before merging confirmed
changes and this record into main. No phone access, installation, push or merge
was performed for this follow-up. Display remains Partial; this package has no
new clean-install evidence and is not a promotion to Works.

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
