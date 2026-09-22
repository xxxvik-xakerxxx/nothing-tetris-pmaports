# SCP loader: implemented contract and research

Status: **Partial**, with READY and real sensor samples on r167.
[Sensor architecture](SCP_SENSOR_BRINGUP.md) and
[desktop evidence](SENSOR_DESKTOP_INTEGRATION.md) cover consumers.
The authoritative U-Boot implementation and exact secure-call trace are in
[the loader document](https://github.com/xxxvik-xakerxxx/u-boot/blob/master/doc/board/mediatek/tetris-scp-loader.rst).

## Provenance

- Installed U-Boot: `bf75c572e16079a36ab43a032be3360c3e93250c`,
  CI 35718518185, LK SHA256
  `7fd5bb218af3d3371dca59930f320ba98d38ddba6cbf7229851c33ba746d62fe`.
- Audited stock LK first payload: 1681136 bytes, SHA256
  `431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`.
- Pinned ATF payload SHA256:
  `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
- Vendor modules: `ee2be53cb75670b548948636a0db1d1ff112bf12`.

Binary offsets below apply only to those payloads, without the 512-byte LK
header. They are not portable addresses or a compatibility claim for other
firmware/SKUs. No factory blobs, keys or calibration are committed.

## Implemented boot contract

1. Import DT reserved memory before relocating initrd. The prior ordering put
   initrd inside SCP's 0xb8000000/0x2300000 carveout. The fix demonstrated
   non-overlap on three warm boots with USB transfers; this alone was not
   SCP startup evidence.
2. Require exact slot-A ATF/container identities and authenticated component
   metadata. A valid misc A/B record is a consistency check, not proof of
   actual LK slot; fastboot's hard-coded current-slot is not independent proof.
3. Require zero TCM before firmware-memory writes. Reject stale handoff and
   disable the Linux SCP node rather than overwriting a possibly live processor.
4. Validate service-page and DT/LMB ownership, capacities and overlaps;
   authenticate, decrypt through the stock secure service, and verify plaintext.
5. Register the audio shared-memory layout, prepare/reset-hold TCM, validate
   readback and complete secure memory/region-info registration. Kernel startup
   owns reset release; any first error is terminal for that boot.
6. Register logger receive buffers before startup; resolve the existing
   infracfg syscon before READY processing. Do not create a second MMIO owner.

## Secure ABI trace

LK 0x2d038..0x2d07c selects `tinysys-scp-RV55_A` and its DRAM member with
destination limits 0x700000/0xe00000. The section loader at 0x74da0 validates
bounds and dispatches security processing. LK 0x16ea0 returns backend 2 in
this binary. SMC 0xc2000133 maps to ATF handler 0xafcc -> 0x2bff4, not the
adjacent service-table handler. Service-page registration at 0xb0b8 requires
physical 0x48401000 and length <=4096. The lock routine is reached through
0xc200010c; do not infer its invocation simply from Linux having booted.

SCP_BOOT 0xc200040f maps to ATF 0x3b670, not runtime handler 0x3a944.
The initial loader copies 0x2000 bytes to TCM and fills region-info before
secure registration. Copying encrypted partition bytes is not equivalent.

The offline verifier's self-consistent signature result is not trust against
device efuses. Runtime use retains exact-image/profile pins and all integrity
checks; an unlocked bootloader is not justification to bypass authentication.

## Audio memory and bootstrap findings

The r165 first dump identified core1 ASSERT in
`audio_get_common_shared_mem()`, with zero AP address/size. Core1 WFI was
post-assert, not healthy idle. Actual rendezvous bytes are at dump offset
0xe3b24, not the earlier transcription 0xdfb24. Dump SHA256:
`b02bc1be5190c076889d7c0a86b1bd42e2c99f6a50e38500a7e5ec7aef6f6f88`.
DRAM code mapping for that dump is `0x1c8000 + runtime_pc - 0x700000`.

The fix reproduces LK audio-table registration via 0xc2000419 operation 1,
SCP_BOOT operation 8 bank 5 and EMI region 29. Table sizes are logger
0x180000, IPI 0x200000, audio 0x5c0000 and XHCI 0x80000. Total 0x9c0000 is
allocated dynamically through LMB, aligned to 16 MiB below 0xa0000000.
The observed 0x9d000000 allocation is not a driver constant. Bank 5 is not
SCP feature-memory ID 4.

The diagnostic 26 MHz vote alone did not fix the ASSERT. The pinned
0xc2000232 resource service uses operation 1 and a <=7 mask.
`bootstrap_26m=1` keeps the existing vendor request path opt-in; vote lifetime
and idle power remain open. Do not broaden the mask or enable full DVFS
based on delay-loop observations.

## Kernel READY ownership fix

r166 reached the READY handler but `scpreg.scpsys` was absent; logger wake
requests failed and the ready timer continued. r167 patches 0103/0104 use
the existing `mediatek,mt6878-infracfg-ao` syscon at 0x10001000/0x1000,
also owned by power domains, rather than adding a competing vendor mapping.
Wake SET/CLEAR use regmap writes with error propagation. Failed handshakes
must not update awake reference counts as if successful.

## Reproducible sensor evidence

Cold boot `e60a958f-55af-4b19-a2ae-59e294ef10a6`, U-Boot `bf75c572e160`,
CI `35729169169`: one SCP probe with `bootstrap_26m=1` reached recovery
success at 102.550245 and logger re-enable ret=0 at 102.551005/102.551637.
The r166 `scpreg.scpsys` failure and ready-timeout cascade are absent.
Sensorhub was loaded once after checking this stable baseline; the initial
host guard falsely matched the configuration print `scp_awake_timeout`,
and stopped before loading anything. Its corrected check uses the actual
`scp_timeout_times=` failure message. This was not a module reload.

At 279.492084 sensorhub began publishing the 24-entry inventory. Parameters
are ready Y, count 24, physical mask 31. Ten-second captures produced 249
accelerometer, 248 gyro, 249 magnetic, 83 light and 3 proximity events.
Motion/magnetic rates are approximately 25 Hz; proximity data transitions
5/0/5. Gyro/magnetic accuracy remains 0, and the narrow light range does not
yet prove controlled lighting response. No calibration commands were sent.
See SENSOR_INTEGRATION_PATCH.md for the later automatic startup and USB evidence.

Host evidence `/private/tmp/tetris-r167-sensorhub-evidence/` SHA256:

- `accel.jsonl`: `b3347b1227fdfb4a0ab2e08c108bf78bb4be9a368ed4459d80de885635273be7`
- `gyro.jsonl`: `ab5f2892633d928b6a4a0b9c9f72ded2178bce1950a574e092153560f7af5e8e`
- `magnetic.jsonl`: `aaed0f4f6301105171083dbc4b4de1ecfd5ad4a91f156a5a5286b44e0b8b674c`
- `light.jsonl`: `f53ccb3afa16cd6bbfb819e590acb832698b3d42dfd84d988b901c1d6555e77c`
- `proximity.jsonl`: `82a82dfb3d7ce8ebbaca165a2ad2cad4a2d38fc8cf5fb39c16e3bb0e5f59c179`
- `kernel-after-samples`: `214d9fd2fab65325d8d0ecde976ee92d2fd5c9837ea613b443dc94c21fdc8c8d`


## Remaining boundary

Secure preparation and userspace behavior are demonstrated, not general
firmware support. Warm reboot deliberately rejects stale TCM. Safe quiesce,
secure mapping lifetime, three controlled cold starts, clean packaged
consumers, suspend/resume and second-handset validation remain.
