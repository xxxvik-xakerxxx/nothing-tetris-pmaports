# Actual NV record to first constructor

Independent candidate, frozen sources unchanged. Native tests pending CI.
No phone/partition access or per-device calibration was performed or committed.

Pinned B4.1 mnld56d00..57184 selects the legacy reader when de3bc==0. For actual
MT6878 chip string0x6878 the path is
/mnt/vendor/nvdata/md/NVRAM/CALIBRAT/ML4A_000, offset160, length16. This differs
from offset64 on6893/6855/6789; the new reader deliberately supports only6878.
Existing source oracle passed18 exact chip/path/seek/read/close vectors.
Stock short reads leave stale bytes in de490; our reader rejects them.

b41_nv_calibration_read takes the legitimate same-unit CALIBRAT directory
descriptor from the read-only NV mount/export owner. It opens only relative
ML4A_000, verifies a regular non-symlink record before and after open, reads
exactly16 bytes at160 with pread, rechecks identity/size/nanosecond modification
and change times plus current directory entry, then closes once. Outputs remain
unchanged on short read, error, replacement, mutation or close failure.
O_NONBLOCK prevents a replaced FIFO from blocking setup; source owner must
exclude concurrent mutation/replacement/aliases. Filesystem identity checks do
not authenticate device provenance or defeat a malicious mutable provider.
Provider must establish that this is the same unit's legitimate NV record,
not a public OTA or another phone. No fallback, source-write or retry is made.

b41_first_config_from_nv is an actual reader-to-constructor path, not a readiness
mask helper. It requires the real de3bc and de22c producer snapshots selecting
legacy NV and default platform respectively. After complete stable read it adds
only the CALIBRATION input and synchronously calls the frozen first builder.
The sixteen bytes receive calibration provenance at first+3c..4b; XML, remaining
runtime fields and all engine requirements are retained. Already-supplied
calibration is refused rather than silently overwritten. Acquiring legitimate
producer snapshots and mounting/exporting the same-unit NV are supervisor work,
not default-zero permission flags supplied by this helper.

## Alternate branch is not equivalent

de3bc nonzero branches through vendor.debug.gps.valid (1e535),
vendor.debug.gps.c0 (1370f), vendor.debug.gps.c1 (f246), and
vendor.debug.gps.capid.temp (1004f). It writes two words atde490/+4 and a separate
word atde4a0; this is NOT proof of a complete fresh16-byte calibration record.
The unresolved fallback7f960 and preserved state must be audited before that
branch can be implemented or substituted. This candidate refuses it. No
Android-property defaults, calibration zeros or another handset's values are
promoted. SECOND_POLICY and assistance receiver/response closure remain open.

## Main integration and CI

Where the supervisor currently supplies first calibration bytes, it can call
b41_first_config_from_nv with the exact NV directory owner and semantic producer
snapshots. Feed the returned first block through the existing LNA query/runtime
bridge unchanged; retain its partial status and masks. No frozen edits made here.

```sh
CI=true sh "$AUDIT/run_nv_calibration_ci.sh"
```

Ubuntu ASAN/UBSAN and Bionic API28 use the same three-C closure:

```text
b41_nv_calibration.c
b41_first_config.c
test_b41_nv_calibration.c
```

Use C11, Wall/Wextra/Werror, existing sanitizers, and --wrap=pread plus
--wrap=close. No new library dependency. Tests use their own temporary regular
file with synthetic bytes, covering exact offset/data/provenance, unchanged
output, short read, interrupted read, mutation, single-close failure, missing
record, unsupported chip/profile/property branch, duplicate input, truncated
file, FIFO and symlink refusal. They never simulate device readiness or claim
that the currently installed phone takes the legacy branch.
