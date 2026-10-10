# Slot6 typed string and control delivery

Native argument preparation binds the typed callback, and its existing sole
worker selects the matching envelope dispatcher before thread creation.
Native CI is pending. This is actual callback-to-IPC delivery for selectors0/1,
not a working assistance daemon, GNSS fix or engine readiness claim.

## Exact B4.1 contract

mnld SHA285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83:

- 5faac and5fadc mask selector to16bits. Original x2 is saved in x19.
- Active receiver88bf4==0 refuses0/1/3/7 before sending anything. Native
  backend ownership must not be confused with that Android flag; this candidate
  does not write it or claim an assistance service exists.
- Selector0 at5faf4 tests only low16(parameter); zero means no pointer read,
  no packet and zero return. Nonzero passes the original pointer to39490.
- 39490/35630 calls strlen on nonNULL input. NULL is absent, empty is present
  with length1. Exact packet is u32LE1,u32LE150,presence, optionally
  u32LE(strlen+1),string,NUL. No data length comes from parameter.
- Selector1 at5fc30..5fc54 calls39540 regardless of parameter/pointer. It
  produces u32LE1,u32LE152. It is NOT engine start/stop.
- Stock may log and mask a send failure to zero. Our asynchronous backend
  instead preserves first causal failure. Zero callback return means copied
  into the real queue, never assistance success or GNSS completion.

The old adapter's parameter-as-length slot6 handling cannot be reused here.
New callback scans the borrowed legitimate string only up to the host event
limit, serializes synchronously using the existing proven envelope constructor,
and copies the complete typed packet into the SAME initialized adapter queue.
No extra worker/queue, retained vendor pointer, callback socket write or native
engine reentry. NULL/empty remain different.1010-byte strings fit; oversize is
a sticky error, not vendor-like truncation with an inconsistent length field.

Dispatcher validates the entire frame before calling the existing owned IPC
service.150 presence0 must have extent9. Presence1 requires a nonzero extent,
exact final NUL and no earlier NUL;152 must have extent8. Unknown/raw/partial
frames refuse. Other queue kinds delegate to the existing navigation dispatcher
so frame3/4/5 and distinct app/raw streams retain their existing behavior.
Selectors other than0/1 fail sticky; selector15 is not a fake receiver stop.

## Native Integration

The native owner now performs both operations:

1. In native preparation, after native control binding and before constructing
   arguments/starting the worker, call b41_slot6_service_bind(&o->adapter,
   &callbacks), propagating failure through the existing child-exit path.
2. Before starting the single existing worker, select
   b41_slot6_service_dispatch. It delegates all non-slot6 kinds. Existing
   standalone worker callers keep their original navigation dispatcher.

Link the new implementation alongside existing adapter/agps_host/output; keep
the accepted process-lifetime owners and supervised child teardown. No new
readiness flags. FIRST_CONFIG, SECOND_POLICY and AGPS_RECEIVER remain intact.
Full selector3/5/7/LPP/RTCM service effects and actual assistance/frame-sync
receiver/responses still need source-backed implementation; routing150/152 to
a socket alone does not resolve them. No public asset contains per-device clock
calibration; this change uses none and invents no XML/default/secondary policy.

## CI

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_slot6_string_producer.py" \
  "$ASSETS/vendor/bin/mnld"
CI=true sh "$AUDIT/run_slot6_service_ci.sh"
```

Offline oracle needs pyelftools+Unicorn and the existing cleaned-up Machine.
It passed26 active parameter/pointer routes and2 receiver-off refusals against
the pinned binary. Existing test_b41_agps_packets.py independently proves the
strlen/optional-string serializer, including NULL/empty/CR/CRLF.

Native fixture requires pthread and the following six C files (Ubuntu ASAN/
UBSAN; same closure also compiles under Bionic API28 with existing policy):

```text
b41_slot6_service.c
b41_startup_adapter.c
b41_agps_host.c
b41_navigation_output.c
b41_frame_worker.c
test_b41_slot6_service.c
```

Seven isolated process fixtures cover copied lifetime, low16 masking, ignored
pointer routes, NULL/empty/152 exact real datagrams, maximum size and oversize,
malformed packet refusal without send, queue exhaustion, unsupported controls,
peer disappearance and real callback/worker/socket delivery plus bounded
unused-worker teardown. No simulated successful GPS/engine/assistance receiver.
Bound callback/IPC storage lives until fixture child exit; no unsafe unbind.
