# Nothing CMF Phone 1: postmarketOS

Experimental postmarketOS overlay for `nothing-tetris` (A015, MT6878 /
Dimensity 7300), Linux 6.18 and Phosh. Not a daily-driver release.

## Status

Native display and touch are usable; the redraw flicker fix is in main.
Display is currently 60 Hz with software rendering. Sensors provide live
rotation, light and proximity behavior through standard iio-sensor-proxy,
with guarded cold-boot startup. Calibration and lifecycle remain incomplete.

Wi-Fi, Bluetooth, audio, charging, haptics and torch have partial support.
GNSS has transport progress but no verified position fix. Cellular service,
camera capture and GPU acceleration are not working.

[Current status and tested versions](docs/PORT_SUMMARY.md) |
[Research and developer documentation](docs/README.md) |
[Remaining work](docs/PORT_COMPLETION_PLAN.md)

## Sources

- This repository: `main`, containing the overlay, integration packages,
  patches, tests and CI configuration.
- [U-Boot](https://github.com/xxxvik-xakerxxx/u-boot): `master`.
- [Pinned Nothing OS 4.1 sources](docs/NOTHINGOSS_SOURCES.md).
- Retired remote branches are preserved under `archive/2026-09-22/*` tags.
  Archived experiments are not implicitly part of the default image.

## Build and validation

Build kernel and install images through the repository's GitHub Actions
`CI` workflow. The separate `sensor-proxy` workflow builds/tests the sensor
backend package. A successful build is not hardware validation.

Cheap local source validation:

```sh
sh scripts/validate-pmaports-overlay.sh
```

Verify the selected artifact's source commit, BUILD-MANIFEST and SHA256SUMS
before installation. A clean userdata flash destroys its contents. Preserve
stock firmware/calibration partitions and the recovery slot.

The CI manifest's generic minimum U-Boot is not the sensor-ready profile.
Use the exact loader prerequisites in
[the sensor startup guide](docs/SENSOR_INTEGRATION_PATCH.md); do not downgrade
the working SCP loader based only on that generic minimum.

## Layout

- `pmaports/`: device, kernel and firmware overlay.
- `integrations/sensor-proxy/`: native HF backend and optional APK.
- `patches/`: subsystem prerequisites and source-level validation.
- [`scripts/`](scripts/README.md), `ci/`: validation, diagnostics and build configuration.
- `docs/`: current status, maintained research and reproducible test boundaries.

No factory calibration, unique device identity, firmware dumps or generated
images belong in this repository.
