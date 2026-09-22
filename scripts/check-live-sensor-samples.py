#!/usr/bin/env python3
"""Manual HF inventory/sample capture for the pinned Nothing OS 4.1 ABI.

Run on the phone only after a successful, stable SCP and sensorhub probe.
Does not load modules, calibrate, reset firmware, or write persistent state.
Default: inventory only. --sample enables one sensor temporarily.
"""

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import select
import struct
import time


SENSORS = {"accel": 1, "magnetic": 2, "gyro": 4, "light": 5, "proximity": 8}
PACKET_SIZE = 68
INFO = struct.Struct("<B3xI16s16s")
EVENT = struct.Struct("<qBBBx16i")
COMMAND = struct.Struct("<BBBB48s")


def request(fd, number, sensor=0):
    # asm-generic ioctl encoding used by aarch64 Linux.
    packet = bytearray(PACKET_SIZE)
    packet[0] = sensor
    code = (3 << 30) | (PACKET_SIZE << 16) | (ord("a") << 8) | number
    fcntl.ioctl(fd, code, packet, True)
    return packet


def info_decode(packet, expected):
    sensor, gain, name, vendor = INFO.unpack_from(packet, 4)
    if sensor != expected or not gain:
        raise ValueError("invalid sensor identity/gain")
    return {"sensor": sensor, "gain": gain,
            "name": name.split(b"\0", 1)[0].decode("utf-8", "replace"),
            "vendor": vendor.split(b"\0", 1)[0].decode("utf-8", "replace")}


def command(sensor, enable, hz):
    batch = struct.pack("<qq", round(1_000_000_000 / hz), 0)
    return COMMAND.pack(sensor, int(enable), len(batch), 0, batch.ljust(48, b"\0"))


def control(fd, sensor, enable, hz):
    data = command(sensor, enable, hz)
    result = os.write(fd, data)
    # This vendor fop returns the device callback status (0), not byte count.
    # Never retry a successful zero-byte result as a generic write loop would.
    if result not in (0, len(data)):
        raise OSError("unexpected HF control result: " + str(result))


def events_decode(data):
    if len(data) % EVENT.size:
        raise ValueError("partial HF event record")
    for values in EVENT.iter_unpack(data):
        timestamp, sensor, accuracy, action, *words = values
        if timestamp <= 0:
            raise ValueError("invalid sensor timestamp")
        yield {"timestamp_ns": timestamp, "sensor": sensor,
               "accuracy": accuracy, "action": action, "raw": words}


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def capture(fd, name, info, seconds, hz):
    sensor = SENSORS[name]
    samples = []
    poller = select.poll()
    poller.register(fd, select.POLLIN | select.POLLERR | select.POLLHUP)
    control(fd, sensor, True, hz)
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            remaining = max(1, math.ceil((deadline - time.monotonic()) * 1000))
            for _, flags in poller.poll(min(remaining, 500)):
                if flags & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
                    raise OSError("HF device lost during capture")
                for event in events_decode(os.read(fd, EVENT.size * 128)):
                    emit({"event": event})
                    if event["sensor"] != sensor or event["action"] != 0:
                        continue
                    if samples and event["timestamp_ns"] <= samples[-1]["timestamp_ns"]:
                        raise ValueError("non-increasing sensor timestamps")
                    samples.append(event)
    finally:
        control(fd, sensor, False, hz)
    if not samples:
        raise RuntimeError("no DATA_ACTION samples; sensor is not verified")
    dimensions = 3 if name in ("accel", "gyro", "magnetic") else 1
    span = (samples[-1]["timestamp_ns"] - samples[0]["timestamp_ns"]) / 1e9
    emit({"summary": {"name": name, "count": len(samples),
          "observed_hz": (len(samples) - 1) / span if span else None,
          "raw_min": [min(s["raw"][i] for s in samples) for i in range(dimensions)],
          "raw_max": [max(s["raw"][i] for s in samples) for i in range(dimensions)],
          "gain": info["gain"],
          "limit": "Samples alone do not prove calibration or lifecycle support"}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=SENSORS)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--hz", type=float, default=25)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60 or not 1 <= args.hz <= 50:
        parser.error("capture must be 1..60 seconds and 1..50 Hz")
    params = Path("/sys/module/sensorhub/parameters")
    if (params / "firmware_ready").read_text().strip() != "Y":
        raise RuntimeError("sensor firmware inventory is not ready")
    if int((params / "sensor_count").read_text()) <= 0:
        raise RuntimeError("empty sensor inventory")
    emit({"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
          "kernel": os.uname().release, "sample": args.sample})
    fd = os.open("/dev/hf_manager", os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not request(fd, 8)[4]:
            raise RuntimeError("HF manager not ready")
        inventory = {}
        for name, sensor in SENSORS.items():
            if request(fd, 1, sensor)[4]:
                inventory[name] = info_decode(request(fd, 6, sensor), sensor)
                emit({"inventory": {"class": name, **inventory[name]}})
            else:
                emit({"missing": name})
        if args.sample:
            if args.sample not in inventory:
                raise RuntimeError("requested sensor absent")
            capture(fd, args.sample, inventory[args.sample], args.seconds, args.hz)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
