# GNSS bring-up

Status: **Partial, transport only**. No verified satellite fix, NMEA/GeoClue
provider or production autostart. Installed versions live in
[PORT_SUMMARY.md](PORT_SUMMARY.md); protocol research is in
[GNSS_USERSPACE_BRIDGE_AUDIT.md](GNSS_USERSPACE_BRIDGE_AUDIT.md).

## Implemented boundary

The package uses stock-derived v051 from Nothing OS 4.1 connectivity commit
`e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. Patch 0020 supplies the platform
device; firmware is `connsys_gnss_mt6878_mt6631.bin`. The explicit
`nothing-tetris-gnss-transport.service` registers transport without opening
links. No modem driver is required for this narrow gate.

The loader must publish GPS EMI 0x86a00000/0x100000 after secure mapping.
v051's ATF identifier is `MTK_SIP_SMC_CMD(0x537)`. Defining it for compilation
does not prove all secure operations exist on a different firmware profile.

## Strongest hardware evidence

Clean r155, CI 34589225716, passed supervised BINFO/download/stop on three
separate boots: DOWNLOAD_COMPLETE, STOP_WRITTEN, CLOSED and
OFF -> ON -> RST -> WORK -> RST -> OFF. No gpsdl owner remained; exact
32 MiB USB transfers passed. That test used loader c931695 rather than the
manifest's generic minimum, so bootchain portability is still open.

On r156 CI 34692383850, explicit transport start created gps_emi, gpsdl0 and
gpsdl1. The bounded read-only probe returned status 0, code_size 42505 and
fragment_count 106, redacted its cipher key, closed link0 and preserved USB.
It did not submit firmware fragments or start navigation.
The warning `emi_mng_get_gps_emi failed to find gps node` still needs
source-level cleanup despite the later successful supervised cycle.

These are dated transport results, not a new GNSS test on r167.

## Userspace ownership

The ABI is not NMEA. Boot metadata uses secure operation 0x1f; fragment
submission 0x20 carries a selector/index, not a userspace firmware buffer.
The source NMEA channel belongs to MCUDL, disabled in this v051 build.

The packaged read-only helper requires `--probe-link0`, has an eight-second
deadline, allows only ioctls 13/23/28 and performs no device read/write.
Opening link0 still changes hardware power state. A closed fd alone is not
proof of a healthy DSP shutdown: inspect the state transition and owners.

Keep one SSH control session, capture the first failure and power-cycle after
assert, timeout, leaked owner or radio/USB regression. Never replace v050 with
v051 in a live loaded session or unload/reload conninfra.

## Next research gate

Resolve startup command ownership, MVCD/navigation payload semantics and
the standard Linux position-provider boundary against exact B4.1 inputs or
a bounded known-good Android trace. Then demonstrate a timed accurate fix,
repeat cold starts, restart, coexistence and suspend/resume.

Matching mnld/libmnl inputs already exist locally with recorded provenance;
another vendor image is not the missing navigation implementation.
