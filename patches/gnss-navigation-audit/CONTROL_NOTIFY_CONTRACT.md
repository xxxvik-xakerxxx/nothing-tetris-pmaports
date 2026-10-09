# B4.1 callback0 event7 implementation

Scope: `b41_control_notify.c/.h`, native fault fixture, standalone CI runner,
and `test_b41_control_producer.py`. Frozen adapter/query/LNA files unchanged.

Evidence is private B4.1 mnld SHA256
`285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`.
The test verifies that hash via the existing Machine loader, executes only
bounded instruction ranges, and intercepts all external calls. No engine runs.

## Actual producer and transport

- Event7 target `5df28..5dfb4`: global byte `88a55` bit4 suppresses send.
  Otherwise serializer `35410` writes u32LE3, then `36b40` transmits it.
  Literal `9c14` is `mnld_gps_control_socket`.
- `36b40..36d68`: socket AF_UNIX/SOCK_DGRAM; fcntl enables O_NONBLOCK;
  zeroed sockaddr110bytes has family1 at0 and abstract name at3.
  `36bc4..36bd0` zero the entire address, `36bd4` copies name,
  `36be4` terminates final byte, `36c04` sets address length110.
- Dynamic PLT relocations confirm `85350=socket`, `85380=close`,
  `853a0=fcntl`, `853b0=sendto`. Offline tests capture exact sockaddr/payload
  for successful, short and failing send and check each fd is closed once.
- OEM retries EINTR and sleeps/retries EAGAIN. New host path intentionally
  uses one nonblocking send, no retry/reset, and preserves the first error.
  SOCK_CLOEXEC and MSG_NOSIGNAL are host lifetime protections, not recovered
  OEM flag values. Full sockaddr size/address bytes remain exact.

## Executable path and caller boundary

`b41_control_notify(7, actual_runtime_policy)` constructs and sends the real
packet. Return0 means datagram accepted only; return1 means OEM suppression;
negative errno means failure. Caller must propagate failure and treat1 as a
distinct suppressed result, not promote engine/navigation readiness. Runtime
policy must be supplied by its legitimate owner, never guessed zero.

The function opens a local nonblocking CLOEXEC fd and closes it before return;
no shared fd/retained pointer, so independent calls may execute concurrently.
No ownership of the receiver or permission to read its messages is asserted.
A missing listener returns the actual send error. Calls never create/bind a
fake receiver to swallow notifications.

Native standalone CI runner `run_control_notify_ci.sh` uses ASAN/UBSAN and
linker syscall interception. It checks every policy byte, unsupported events,
socket failure, EAGAIN, EINTR, short send, close failure and first-error priority.
Local native compilation is prohibited; this fixture has not been compiled.
The pinned offline producer test passed locally with syscalls intercepted.

## Remaining mandatory effects

This is a complete event7 send branch, not a completed callback0 replacement.
Frozen adapter still refuses active notifications until main coordinates its
integration. This sidecar is worker-side service code, not a callback binding.

- Event0 additionally calls `85890` and publishes/persists position: not served.
- Event3 reads ADC fd, writes ADC.txt and processes the capture: not served.
- Event13 invokes restart path `55220`: not served; no guessed engine stop.
- Events3..5 frame requests have TX but not receiver/result ownership.
- Callback6 structured selectors and receiver/result lifecycle remain unresolved.
- First-config27bytes/XML, complete second policy, gpsdl transport ownership,
  and bounded native engine stop remain required before mnl_run.

Next gates: native sanitized test on Linux/Bionic, then exact receiver-owner
integration and end-to-end delivery. No hardware success or GNSS fix claimed.
