# Documentation

Use [PORT_SUMMARY.md](PORT_SUMMARY.md) for current hardware status, exact
tested versions and CI state. [PORT_COMPLETION_PLAN.md](PORT_COMPLETION_PLAN.md)
contains only remaining work and validation requirements.

## Active research

| Topic | Entry point | Supporting contract |
| --- | --- | --- |
| Display | [Native path and open PQ work](DISPLAY_FIRST_FRAME_AUDIT.md) | Packaged route/frame-end fixes versus inactive POSTMASK candidate |
| Sensors | [Architecture](SCP_SENSOR_BRINGUP.md) | [Startup](SENSOR_INTEGRATION_PATCH.md), [desktop backend](SENSOR_DESKTOP_INTEGRATION.md), [secure loader](SCP_LOADER_TRACE.md) |
| GNSS | [Bring-up](GNSS_BRINGUP.md) | [Userspace/transport research](GNSS_USERSPACE_BRIDGE_AUDIT.md) |
| Modem | [Boot-chain and SIM research](MODEM_SIM_EVIDENCE_PLAN.md) | [Util](CCCI_UTIL_COMPILE_ONLY.md), [core](CCCI_CORE_COMPILE_ONLY.md), [CCIF](MODEM_CCIF_COMPILE_ONLY.md), [common](MODEM_COMMON_COMPILE_ONLY.md), [FSM/DPMAIF](MODEM_FSM_PORT_DPMAIF_COMPILE_ONLY.md) |
| GPU | [Dependencies](GPU_BRINGUP.md) | [Panthor compile boundary](PANTHOR_COMPILE_ONLY.md) |
| Cameras | [Pipeline/ownership](CAMERA_BRINGUP.md) | [Compile-only gate](CAMERA_COMPILE_ONLY_AUDIT.md) |
| Power | [Charging and idle](POWER_CHARGING_BRINGUP.md) | [BC1.2 decode](MT6375_BC12_COMPILE_ONLY.md), [lifecycle](MT6375_BC12_LIFECYCLE_COMPILE_ONLY.md) |
| USB | [Stable identity](USB_STABLE_IDENTITY.md) | Per-device derivation and reconnect gates |

## Source and packaging

- [Pinned official sources](NOTHINGOSS_SOURCES.md).
- [Driver ownership and integration strategy](DRIVER_STRATEGY.md).
- [Kernel patch map](PATCH_SERIES.md).

Compile-only documents describe reproducible source boundaries, not working
hardware. Their old command outputs are evidence for those boundaries, not
the currently installed version. Prefer the implementation and CI for exact
commands; builds for this port run in CI.

Superseded installation diaries remain in Git history at `b66301c` and older
commits, not duplicated in the current tree. Retired remote experiments are
available under `archive/2026-09-22/*` tags. Local capture paths identify
evidence held by the maintainer; they are not public downloadable files.
