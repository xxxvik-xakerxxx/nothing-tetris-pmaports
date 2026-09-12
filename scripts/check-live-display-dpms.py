#!/usr/bin/env python3
"""Bounded user-session DPMS test; not suspend or pixel correctness proof.

Run next to measure-drm-sequence.py as the active desktop user with its
DBUS_SESSION_BUS_ADDRESS. Does not modeset directly, load modules or reboot.
Keep physical power-key/user activity out of the test interval.
"""

import argparse
import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

sys.dont_write_bytecode = True
GET_SEQUENCE = 0xC018643B


def get_sequence(fd, crtc):
    request = bytearray(struct.pack("=IIQq", crtc, 0, 0, 0))
    try:
        fcntl.ioctl(fd, GET_SEQUENCE, request)
    except OSError as error:
        if error.errno == errno.EINVAL:
            return None
        raise
    _, active, sequence, timestamp = struct.unpack("=IIQq", request)
    return {"active": bool(active), "sequence": sequence, "timestamp_ns": timestamp}


def wait_transition(fd, crtc, connector, enabled, timeout):
    start = time.monotonic()
    deadline = start + timeout
    inactive_queries = 0
    samples = 0
    while True:
        state = connector.read_text().strip()
        if state not in ("enabled", "disabled"):
            raise ValueError(f"unexpected connector state: {state}")
        sequence = get_sequence(fd, crtc)
        samples += 1
        if sequence is None:
            inactive_queries += 1
        ready = (state == "enabled" and sequence is not None and sequence["active"])
        off = (state == "disabled" and (sequence is None or not sequence["active"]))
        if (ready if enabled else off):
            return {"ready_ms": (time.monotonic() - start) * 1000,
                    "samples": samples, "get_sequence_einval": inactive_queries,
                    "sequence": sequence}
        if time.monotonic() >= deadline:
            raise TimeoutError(f"DPMS {'on' if enabled else 'off'} not ready; "
                               f"samples={samples}, GET_SEQUENCE EINVAL={inactive_queries}")
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))


def emit(**record):
    print(json.dumps({"monotonic_ns": time.monotonic_ns(), **record}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crtc", required=True, type=int)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--device", default="/dev/dri/card0")
    parser.add_argument("--connector", type=Path,
                        default=Path("/sys/class/drm/card0-DSI-1/enabled"))
    args = parser.parse_args()
    if not 1 <= args.cycles <= 10 or not 0 < args.crtc < 2**32:
        parser.error("cycles must be 1..10 and CRTC a positive u32")
    from gi.repository import Gio, GLib

    spec = importlib.util.spec_from_file_location(
        "cadence", Path(__file__).with_name("measure-drm-sequence.py"))
    cadence = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cadence)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(destination, path, interface, method, parameters):
        return bus.call_sync(destination, path, interface, method, parameters,
                             None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def session(method, parameters):
        return call("org.gnome.SessionManager", "/org/gnome/SessionManager",
                    "org.gnome.SessionManager", method, parameters)

    def power(mode):
        call("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
             "org.freedesktop.DBus.Properties", "Set",
             GLib.Variant("(ssv)", ("org.gnome.Mutter.DisplayConfig", "PowerSaveMode",
                                     GLib.Variant("i", mode))))

    cookie = None
    fd = None
    success = False
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_CLOEXEC)
        baseline = get_sequence(fd, args.crtc)
        emit(stage="baseline", kernel=os.uname().release, crtc=args.crtc,
             connector=args.connector.read_text().strip(), sequence=baseline)
        if baseline is None or not baseline["active"]:
            raise ValueError("wake the display before starting; baseline must be active")
        cookie = session("Inhibit", GLib.Variant("(susu)",
                         ("tetris-display-gate", 0, "Bounded display lifecycle test", 8)))[0]
        if not session("IsInhibited", GLib.Variant("(u)", (8,)))[0]:
            raise ValueError("session idle inhibition not active")
        emit(stage="idle-inhibited")
        for cycle in range(1, args.cycles + 1):
            for mode, enabled in ((3, False), (0, True)):
                power(mode)
                transition = wait_transition(fd, args.crtc, args.connector, enabled, 3)
                emit(cycle=cycle, stage="on-ready" if enabled else "off-ready", **transition)
            # No retry: any queue error, timeout or discontinuity ends the gate.
            result = cadence.measure(args.device, args.crtc, 30, 3)
            emit(cycle=cycle, stage="frames", **result)
        success = True
    except Exception as error:
        emit(stage="FAIL", error=str(error))
    finally:
        # Leave failed power state untouched so first-failure evidence survives.
        if fd is not None:
            os.close(fd)
        if cookie is not None:
            try:
                session("Uninhibit", GLib.Variant("(u)", (cookie,)))
                emit(stage="idle-inhibitor-released")
            except Exception as error:
                emit(stage="FAIL-cleanup", error=str(error))
                success = False
        bus.close_sync(None)
    if success:
        emit(stage="PASS", cycles=args.cycles, scope="DPMS and sequence events only")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
