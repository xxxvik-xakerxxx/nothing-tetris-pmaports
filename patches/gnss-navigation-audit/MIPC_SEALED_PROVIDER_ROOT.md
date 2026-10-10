# B4.1 sealed provider root

Source artifact CI38039798135 at4e73: release Tetris_B4.1-260415-1709,
system image SHA256 ce53560d05e6caa8ad8c27a4c85eefbb93479b879e8c610be650be6b689108e6.
Actual system/lib64/liblog.so is102352 bytes, SHA256
dce4ece329f925cdc0b181b3e5f11b54d92a24e49b1b90b121a4e0f960df84fd.
Trust is pinned mirror archive identity plus independent library pins, NOT OEM
signature verification. No NDK import stub is accepted as liblog.

## Resource integration

`acquire_providers(stock_root, bionic_root)` reuses frozen acquire/version
validation with the fixed real liblog pin. The actual ten providers resolve385
bindings, zero missing libraries and zero required symbol errors. Weak symbols
retain existing reporting. Both mtkrillog LIBLOG imports bind to real liblog.
No property service, runtime namespace, modem readiness or INIT is certified.

`LoaderResources` reuses SealedStage; hashes sealed copies before returning
fixed-order descriptors. Linker mode0555 and library modes0444 admit legitimate
read/map/execute access after privilege drop. Source lease is closed only after
copies exist. Move transfers ownership once to the parent's supervisor.
Prepare failure leaves descriptors caller-owned; successful prepare moves them.
Forked child reads supervisor's retained stage array in the same fixed order.

`b41_mipc_loader_root` creates its own private mount namespace and fresh tmpfs
under a fresh, empty root-owned directory controlled exclusively by the parent.
The parent must own/protect this directory and its ancestors through handoff;
it is not an attacker-controlled path or shared mutable staging tree. Fixed
paths contain bounded copies read directly from the actual sealed FDs, never
mutable source-path reopens. Aggregate size and tmpfs are limited to64MiB;
copies use a64KiB buffer and exact source length. The entire snapshot is
remounted read-only before privilege drop or execution. Original sealed
descriptors remain parent-owned until terminal reap. All directories and root
are read-only for the eventual child.
`ld-android.so`'s provider is the actual pinned linker64 at its executable path.
Partial failure requires child exit; there is no mount rollback/reinit on a live
worker. Parent retains descriptors until EXITED/SIGNALED terminal reap using the
existing corrected supervisor. No forced exit is described as an RX join.

CI38048441911 rejected the former anonymous-memfd MS_BIND implementation with
EINVAL before bind-remount fault injection. That implementation was not usable.
The adapter now consumes the private read-only snapshot directly and retains
existing proc/chroot/drop/seccomp/bounds without an extra root bind.
This bundle does NOT modify or run the frozen isolate. The separate adapter
below supplies an independently pinned /probe and libmnl via sealed descriptors.
INIT remains prohibited pending config, property and actual
modem/CCCI readiness contracts; no property or transport fakes are added.

## CI commands and dependencies

Set TETRIS_B41_STOCK_ROOT to the existing extracted stock artifact root and
TETRIS_BIONIC_ROOT to the legitimate pinned runtime root. No archive download
is needed. `PYTHONDONTWRITEBYTECODE=1 python3 test_b41_mipc_provider_resources.py`
requires pyelftools and runs real closure tests without C or ELF execution.
Mac explicitly skips the Linux sealing vector; it does not claim a sealing pass.

`CI=true sh run_mipc_loader_resources_ci.sh mounts` requires Linux memfd, Ubuntu native
compiler/sanitizers, timeout, and root/CAP_SYS_ADMIN for the child-only mount
fixture. No asset is executed: native fixture uses labelled non-ELF filesystem
data only. Pinned real bytes are tested by the Python sealing vector. Add Bionic
API28 object compile of b41_mipc_loader_root.c to parent's existing native build.
No local C compilation, namespace operation or phone call was performed.

`CI=true TETRIS_B41_STOCK_ROOT=... TETRIS_BIONIC_ROOT=... sh
run_mipc_loader_resources_ci.sh providers` is an independent asset-required
mode. The mount mode does not import Python resource audits or require cached
stock artifacts; it also compiles the separate immutable isolate adapter object.
Neither mode silently skips missing CI prerequisites.

Cleanup faults are attached to the original producer exception using add_note;
they never replace its errno. Offline vectors cover validation, staging and
mode failure with failing cleanup. Native mount vectors impose actual kernel
seccomp EACCES on tmpfs creation and the final read-only remount. They check
unchanged parent root, retained supervisor FDs before exit, original mount error
through the report pipe, and FD release only after terminal child reap.

## Separate immutable executable adapter

`ProbeResources` appends two fully sealed descriptors to the ten providers:
the existing CI37898372984 load-only probe (SHA256
011a0dd90ab2043fd2eb8312024f000769d093b8e1b58e0e3540509122e7c214)
and libmnl (SHA256
3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90).
No caller-selected executable, hash, mutable reopen or replacement stub is
accepted. `b41_mipc_loader_root_probe` snapshots these at fixed paths. The distinct
`b41_mipc_sealed_probe_spawn` reuses the frozen isolate's actual filter/control,
cgroup check and resource limits without an extra root bind.
Call only from a dedicated root launcher: network/PID namespace creation changes
that launcher. Its prepared supervisor owns all twelve FDs and the absolute
deadline, checked before namespace/fork; finish/reap remains mandatory after any
bind attempt, including failed bind. Unreaped children retain the lease. A
deadline expiring during startup is enforced by the parent's existing waiter.

The adapter offers only control or the original dlopen-only executable. It does
not supply property services, CCCI handshake, configuration or engine INIT/RX.
Load/control execution has NOT been tested locally. For CI object validation:
`cc -std=c11 -Wall -Wextra -Werror -I. -c b41_mipc_sealed_isolate.c`.
Executable linkage needs b41_mipc_loader_root.c, b41_mipc_supervised_child.c,
b41_native_receiver_host.c and parent's entry point; use function/data sections
and linker garbage collection for the native host's unused functions. The
frozen mnl-isolate.c include is an explicit source dependency. This adapter is
Linux-only, not an Android API28 namespace library. Validate Python admission
with `PYTHONDONTWRITEBYTECODE=1 python3 test_b41_mipc_probe_resources.py` using
the same explicit stock/Bionic roots; actual sealing vectors require Linux.

## Separate sealed OEM XML snapshot

`ProbeXmlResources(stock_root, bionic_root, xml_artifact)` extends only the
existing resource producer, appending the single fixed vendor XML as FD slot12
after the unchanged ten providers, probe and libMNL. It reads exactly
`xml_artifact/vendor/etc/MNL_Config.xml` through one O_NOFOLLOW/CLOEXEC source
FD, uses existing seal_provider to copy and verify the fully sealed bytes
against independent B4.1 SHA256
`7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31`,
requires5087 bytes and mode0444, then closes the source FD. Source stats or
paths do not authenticate the resulting bytes. No caller-supplied pin, XML
payload, output path, property or hardware-permission flag is accepted. This
is pinned mirror/archive evidence, not an OEM signature claim. The existing
move/close lifetime handles all thirteen FDs and preserves the first failure
if cleanup also fails. Move is single-use; caller owns the returned array
until successful supervisor_prepare transfers it. Never close it after bind
until terminal EXITED/SIGNALED reap; errors/STOP are not lease release.

The distinct `b41_mipc_loader_root_probe_xml(root, providers, 10, probe, mnl,
xml)` extends the existing private snapshot copier, not a duplicate root
builder. It preflights seals, fixed mode/size, duplicate identity and the SAME
64MiB aggregate bound before any namespace operation. It adds just
`/vendor/etc` mode0555 and `/vendor/etc/MNL_Config.xml` mode0444, copying exact
sealed FD bytes before the whole tmpfs becomes read-only. The C boundary
checks shape/seals, NOT SHA authenticity: only ProbeXmlResources-admitted
leases may reach it. No mutable source-path reopen, arbitrary asset slot,
symlink, GPIO/device node or service stub is introduced.

The actual path comes from the pinned mnld directory producer +0x406 and
libMNL filename literal181e2, not from preinitializing globals. See the frozen
[read-profile source contract](xml-policy-draft/XML_READ_PROFILE.md). This
fresh private root has NO `/data`, establishing preferred-file absence by
construction rather than by omission from an artifact. The source selector
therefore chooses the pinned vendor file with policy7; the absent data-write
destination cannot succeed, and the actual reader's fail-write branch clears
only bit2, retaining READ/SET. These are source-backed expected branches,
not a claim that the native reader has executed in this snapshot.
Per-device NV/calibration is not copied, overwritten or generalized here.

The original10-provider and12-FD root APIs retain the original target set and
do not create `/vendor/etc`. The existing load-only CLI/parent/isolate remain
UNCHANGED and reject13-FD admission. Do not hand the extended resources to
that launcher. A future reviewed GNSS caller must transfer thirteen FDs into
the existing supervisor and invoke the new snapshot API in its owned child;
this extension provides no new spawn/exec, engine INIT, CCCI handshake or
property permissions. It removes the source-to-private-root XML path gap,
not the remaining native navigation readiness gates.

### Focused CI validation

```sh
# Read-only Python admission/fault checks; two Linux sealing vectors required.
CI=true TETRIS_B41_STOCK_ROOT="$SELECTED_STOCK" \
  TETRIS_BIONIC_ROOT="$ORIGINAL_PINNED_BIONIC_PROBE" \
  TETRIS_B41_XML_ROOT="$SELECTED_XML_ARTIFACT" \
  sh run_mipc_loader_resources_ci.sh xml

# Existing native ASAN/UBSAN fixture, now covers both12 and13-FD snapshots.
CI=true sh run_mipc_loader_resources_ci.sh mounts
```

`xml` is a separate asset-required mode: old `providers` mode is unchanged.
Requires Python+pyelftools and actual selected inputs (no download/fallback
or emulator). Native mounts require CI root/CAP_SYS_ADMIN and the existing
native sources/supervisor, as before. Include the updated loader-root object
in the existing Bionic API28 cross-build; do not execute it locally.

Python fixtures check the actual independent XML pin against read-profile
constants, fixed path/mode, missing/size/hash/mode faults, single transfer and
first-error retention. Native fixtures use labelled NON-OEM filesystem bytes
only (not fake authentication or INIT), verify exact copying and EROFS, absence
of data and unchanged legacy targets, reject bad size/seals/mode/alias, inject
an actual XML pread EIO and final remount EACCES, and retain all13 descriptors
until the terminal child reap while the parent's root remains unchanged.

At `359042b9b2bf`, [CI 38074089440](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38074089440)
passed all ten Python ownership tests without skips, including the actual
Linux sealed-pin vectors. The native ARM64 ASAN/UBSAN mount fixture passed
10/12/13-FD roots, XML copying, read-only/failure paths and terminal-reap
lifetime. Downloaded source manifests match the commit. The independent
unchanged Bionic load-only stage also reports `LOAD_OK` and terminal reap;
it does not execute the new XML snapshot or call engine INIT.

Next gate is reviewed executable admission for the thirteen-FD snapshot.
Native reader/SET operation, complete config constructors,
runtime libxml2/OpenSSL, legitimate CCCI/property readiness and RX shutdown
remain separate unresolved gates. No navigation success or INIT claimed.
