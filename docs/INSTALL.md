# Installation and FAQ

Updated: 2026-10-09. For Nothing CMF Phone 1 (`nothing-tetris`, A015) only.
This is an experimental Linux port, not an Android ROM or a daily-driver release.

> **Use at your own risk.** This project is provided as-is, without warranty.
> Flashing can erase all data, prevent booting, or brick your device. To the
> extent permitted by applicable law, the maintainer and contributors accept
> no responsibility or liability for damaged or bricked devices, lost data,
> recovery costs, or other loss resulting from using this project or guide.
> You are responsible for checking compatibility, backups and recovery before
> running any command. Do not proceed unless you accept these risks.

## Quick answers

**Does it have a graphical interface / window manager?** Yes. The image uses
Phosh with the Phoc Wayland compositor. It is not console-only. Display and
touch work on the tested device; GPU acceleration does not, so the desktop
currently uses software rendering. See [hardware status](PORT_SUMMARY.md).

**Is the roughly 900 MB file for userdata?** Only if its name is
`nothing-tetris-root.sparse.img`. That is the Linux root filesystem image,
written to `userdata`. It contains the OS, applications and user files, not
just Android-style user data. Its sparse/download size is not the resulting
filesystem capacity; root expansion is handled during boot.

**What goes into super?** `nothing-tetris-boot.img`, despite the word
"boot" in its name. This port repurposes `super` for its Linux boot filesystem.
Do not flash this file to Android `boot_a`, `boot_b`, `vendor_boot` or `init_boot`.

**Where does the small, roughly 34 MB file go?** Identify it by filename,
not size. If it is `boot_image.itb`, do not flash it separately: it is the
kernel/DT/initramfs FIT payload already included in the boot filesystem.
If it is `nothing-tetris-boot.img`, it goes to `super`. If its name differs,
stop and provide the filename and CI run; do not guess a partition.

## Firmware requirements

The tested development baseline uses Nothing OS 4.1-era Tetris firmware.
An Android custom ROM's name/version does not establish the versions of its
preloader, LK, ATF, SCP or other firmware. This image does not replace all of
those components. There is no verified universal NOS 4.0 or custom-ROM support.

If coming from a custom ROM with unknown firmware, establish the matching
stock NOS 4.1 baseline for your exact device before attempting this port,
using a verified device-specific stock restoration procedure. Do not mix
individual firmware partitions from unrelated builds or handsets. The label
"NOS 4.1" alone is not proof of the exact SCP/ATF profile required by the
experimental sensor loader. If you cannot verify that profile, stop and ask
with your exact stock build and slot information rather than flashing blindly.

Prerequisites:

- Unlocked bootloader and working host fastboot, USB cable and adequate charge.
- Backups of personal data and your own stock firmware/calibration, held off-device.
- Compatible stock restoration files and a recovery method you can actually use.
- A validated Tetris U-Boot image compatible with the selected pmOS build.
  Stock Android fastboot, Android userspace fastbootd and U-Boot fastboot are
  different environments; the install sequence below expects U-Boot fastboot.

Never erase or replace factory `nvram`, `nvdata`, `nvcfg`, `persist`, `proinfo`,
`protect*`, `md_sec`, or firmware/security partitions as a troubleshooting step.
Do not relock the bootloader with this non-stock layout.

## Select and verify artifacts

Download the `nothing-tetris-images` artifact from a successful
[pmOS CI run](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions).
Use all files from the same run; do not mix boot/root images from different builds.

| File | Purpose / destination |
| --- | --- |
| `nothing-tetris-boot.img` | Flash to `super` |
| `nothing-tetris-root.sparse.img` | Flash to `userdata`; destroys its existing contents |
| `boot_image.itb` | Included FIT payload; no separate partition flash |
| `BUILD-MANIFEST`, `SHA256SUMS` | Source identity and integrity checks; never flash |
| `u-boot-tetris-lk.img` | Separate U-Boot artifact for the verified LK slot, not `super` or `userdata` |

From a checkout of this repository, verify the extracted image directory:

```sh
sh scripts/verify-ci-install-artifacts.sh /path/to/extracted/nothing-tetris-images EXPECTED_COMMIT_SHA
```

Replace both arguments with the actual directory and full CI source commit.
The check needs `sha256sum` and `file` on the host. Also verify the separate
U-Boot artifact against its own manifest and checksums. A matching checksum
does not establish hardware/firmware compatibility.

The latest installed image is r173 from
[CI 37797116235](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37797116235),
source `37dc3d03734c2919b8d18c75ac1cf37b94b18694`.
Its archive, image hashes and complete sparse structure were verified before
a clean installation. First boot, USB/SSH, root expansion and installed FIT
verification passed. Visual and sensor cold-start confirmation remain pending;
see the current [checkpoint](PORT_SUMMARY.md#latest-installed-checkpoint-r173).
Sensors are opt-in on a fresh image and require the matching SCP-enabled
loader; the ordinary U-Boot artifact does not enable that profile.

## U-Boot prerequisite

Use the [Tetris U-Boot repository](https://github.com/xxxvik-xakerxxx/u-boot).
Do not flash raw `u-boot.bin` as an LK image. The recorded sensor-ready image
is `bf75c572e16079a36ab43a032be3360c3e93250c`, CI 35718518185, LK SHA256
`7fd5bb218af3d3371dca59930f320ba98d38ddba6cbf7229851c33ba746d62fe`.
It was tested in `lk_a`, with stock `lk_b` preserved.

For that exact validated slot-A setup only, after independently confirming
the active stock slot and recovery path, the LK write is:

```sh
fastboot flash lk_a u-boot-tetris-lk.img
```

Do not apply this to an unknown/B-slot setup or switch slots by guesswork.
U-Boot's reported current-slot is not independent proof of the original
firmware slot. Do not overwrite both LK copies during initial bring-up.
Preserving stock LK alone does NOT preserve a bootable Android installation
after `super` and `userdata` are overwritten.

**Optional: install to both LK slots after validation.** Once the chosen
image has successfully booted Linux and you have verified that you can return
to U-Boot fastboot, you may install that same image to both LK slots, provided
it is compatible with the firmware/boot context of both slots:

```sh
fastboot flash lk_a u-boot-tetris-lk.img
fastboot flash lk_b u-boot-tetris-lk.img
```

Require each write to succeed before continuing. This replaces both stock LK
copies: keep off-device stock backups and an independent recovery method.
The experimental SCP profile is currently validated only for slot A;
successful boot from A does not establish slot-B SCP/firmware compatibility.
Keep B stock until that compatibility is established for the selected image.

Ordinary U-Boot CI builds leave SCP preparation disabled. The explicit SCP
profile needs all three diagnostic inputs and the matching pinned firmware;
the generic minimum U-Boot in the pmOS manifest is not sufficient evidence
for sensor readiness. See [sensor prerequisites](SENSOR_INTEGRATION_PATCH.md).

## Flash the Linux image

**This replaces Android's super contents and erases userdata. It is not
dual boot or an in-place data-preserving update.** Only proceed after the
loader/profile, artifact checks and backups above are complete.

Enter the verified U-Boot's fastboot mode (hold Volume Down as it starts).
With exactly the intended phone attached, check `fastboot devices`, then:

```sh
fastboot flash super nothing-tetris-boot.img
fastboot flash userdata nothing-tetris-root.sparse.img
fastboot reboot
```

Run one command at a time and require each write to succeed. Stop on an
error; do not continue or substitute another partition. Fastboot handles
the sparse image; do not manually unpack/chunk it or format userdata after
writing the image. No separate `boot_image.itb` write is needed.

## First boot and troubleshooting

Expect the Phosh graphical interface, not Android. The current CI build sets
the initial password/PIN to `147147`; change it after login and do not expose
the development image to an untrusted network with default credentials.

Confirm display/touch and USB networking before testing optional hardware.
Sensors remain opt-in, require the prepared cold handoff, and can be disabled
by the intentional stale-TCM guard after warm reboot. Do not remove that guard
or repeatedly reload hardware modules. Cellular service, camera capture and
GPU acceleration are not working; these are not installation mistakes.

If boot fails, retain the exact filenames, CI commit, firmware build, original
slot and complete fastboot output. A BROM/preloader USB loop is not U-Boot
fastboot. Stop repeated writes and use your prepared recovery procedure.
Do not assume flashing Android boot alone restores stock after replacing super.
Never post IMEI, serials, credentials or calibration dumps in an issue.
