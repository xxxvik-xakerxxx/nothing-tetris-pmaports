# Maintained tools

Kernel/image builds run through GitHub Actions. Local Docker/baseline build
wrappers were retired because they did not reproduce the pinned CI inputs.
Build/package helpers used by CI remain here; do not run all scripts as a batch.

## Source and artifact checks

| Task | Tool |
| --- | --- |
| Overlay/package validation | `validate-pmaports-overlay.sh` |
| Apply overlay and kernel config | `apply-pmaports-patches.sh`, `apply-kernel-config-overlay.sh` |
| Verify downloaded install image | `verify-ci-install-artifacts.sh` |
| Verify radio bundle | `verify-radio-live-artifact.sh` |
| Inspect/expand bounded sparse artifact | `inspect_ci_sparse.py` |
| Display routing | `check-mt6878-display-route.sh` |
| GNSS source/protocol boundaries | `check-gnss-boot-protocol.py`, `check-gnss-navigation-boundary.sh`, `check-gnss-v051-readonly.sh` |
| GPU/actuator prerequisites | `check-panthor-compile-only.sh`, `check-panthor-vgpu-readback.py`, `check-pd9302a-compile-only.sh` |
| SCP/inventory/patch contracts | `check-scp-region-host.py`, `check-sensor-list-reply.py`, `check-vendor-patch-application.py` |

Some source gates compile bounded host fixtures or require exact upstream
checkouts; inspect their inputs before use. Tests are under `scripts/tests/`
and `ci/`. Additional subsystem research gates stay beside their patches.

## Device tools

Use one control session and a known recovery path. Live checks are not a
generic smoke-test batch: some affect display, radio or power state. Never
unload/reload hardware-owning vendor modules to retry a failed test.

| Task | Tool |
| --- | --- |
| Collect observations | `collect-live-audit.sh` |
| USB/network regression | `check-live-regression-gate.sh` |
| Cross-subsystem snapshot | `check-live-hardware-frontier-gate.sh` |
| Greeter and display transitions | `check-live-greeter-display-gate.sh`, `check-live-display-dpms.py` |
| DRM cadence | `measure-drm-sequence.py` |
| Audio, charging, thermal, idle | `check-live-audio-gate.sh`, `check-live-power-gate.sh`, `check-live-thermal-gate.sh`, `check-live-idle-delta.sh` |
| Raw sensor samples / desktop properties | `check-live-sensor-samples.py`, `check-live-sensor-proxy.py` |

The hardware-frontier gate's baseline expectations are conservative; it is
not a replacement for opted-in sensor readiness and desktop checks. Use the
subsystem-specific tests for experimental features. Local logs remain under
ignored `local/`; never commit credentials, device identities or calibration.

See [current status](../docs/PORT_SUMMARY.md) and
[research index](../docs/README.md) before hardware experiments.
