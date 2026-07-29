# Nothing CMF Phone 1 postmarketOS overlay

postmarketOS overlay for the Nothing CMF Phone 1 (`nothing-tetris`, model
A015, MediaTek MT6878 / Dimensity 7300).

The repository is intentionally small: it tracks only the device package,
kernel package, patch series, validation scripts, and CI config needed to build
the postmarketOS port. Full upstream source trees, generated images, local
logs, and device backups are not committed.

## Current baseline

- Device package: `device/testing/device-nothing-tetris`
- Kernel package: `device/testing/linux-postmarketos-mediatek-mt6878`
- Kernel package version: `6.18-r52`
- Kernel source commit:
  `d84b264a54a37611f2f46bc19363cb9b41606205`
- Device DTB: `mt6878-nothing-tetris`
- Display: inherited framebuffer exposed to Linux through `simpledrm`; native
  DSI/panel bring-up is not part of this baseline.

Patch grouping and known cleanup debt are documented in
`docs/PATCH_SERIES.md`.

## Layout

- `pmaports/` - overlay files copied on top of upstream postmarketOS pmaports.
- `ci/pmbootstrap-aarch64.cfg` - pmbootstrap config used by CI and local Docker
  helpers.
- `docs/PATCH_SERIES.md` - active kernel patch series map.
- `scripts/validate-pmaports-overlay.sh` - checks APKBUILD local source and
  checksum references.
- `scripts/build-arm64-kernel.sh` - local Docker helper for the kernel package.
- `scripts/build-arm64-image.sh` - local Docker helper for the device image.

## Validate

```sh
./scripts/validate-pmaports-overlay.sh
```

The validator checks tracked local patch/config files against APKBUILD
`sha512sums`. Remote source archives are fetched by pmbootstrap during package
builds.

## Build

Kernel package:

```sh
./scripts/build-arm64-kernel.sh
```

Device image/rootfs:

```sh
./scripts/build-arm64-image.sh
```

Both helpers clone/update upstream `pmbootstrap` and `pmaports` under
`upstream/`, then copy this overlay on top before building.

## CI

GitHub Actions validates the overlay on pushes and pull requests. On pushes it
also builds the device and kernel packages against a fresh upstream pmaports
checkout.
