#!/usr/bin/env python3
"""Bounded real SensorProxy observations, including backlight; no fake readings."""
import argparse
import json
from pathlib import Path
import time


def main():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=45)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 120:
        parser.error("duration must be 5..120 seconds")
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    interface = "net.hadess.SensorProxy"
    obj = bus.get_object(interface, "/net/hadess/SensorProxy")
    proxy = dbus.Interface(obj, interface)
    props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    loop = GLib.MainLoop()
    claimed = []

    def emit(kind, value):
        print(json.dumps({"monotonic": time.monotonic(), kind: value}), flush=True)

    def changed(iface, values, invalidated):
        if iface == interface:
            emit("changed", dict(values))

    def brightness():
        emit("brightness", {p.parent.name: int(p.read_text())
                            for p in Path("/sys/class/backlight").glob("*/brightness")})
        return True

    subscription = bus.add_signal_receiver(
        changed, signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        bus_name=interface, path="/net/hadess/SensorProxy")
    emit("boot_id", Path("/proc/sys/kernel/random/boot_id").read_text().strip())
    emit("initial", dict(props.GetAll(interface)))
    try:
        for name in ("Accelerometer", "Light", "Proximity"):
            getattr(proxy, "Claim" + name)(timeout=5)
            claimed.append(name)
        GLib.timeout_add_seconds(1, brightness)
        GLib.timeout_add_seconds(args.seconds, lambda: (loop.quit(), False)[1])
        loop.run()
    finally:
        for name in reversed(claimed):
            getattr(proxy, "Release" + name)(timeout=5)
        subscription.remove()
        bus.close()


if __name__ == "__main__":
    main()
