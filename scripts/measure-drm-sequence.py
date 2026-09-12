#!/usr/bin/env python3
"""Measure DRM sequence cadence, not compositor FPS or pixel correctness.

Linux arm64/x86 ioctl ABI, from include/uapi/drm/drm.h. No modeset or
register writes; pending events temporarily hold a vblank reference.
An inactive CRTC or competing modeset is an error, never retried.
"""

import argparse
import fcntl
import json
import os
import select
import struct
import sys
import time

QUEUE_SEQUENCE = 0xC018643C
EVENT = struct.Struct("=IIQqQ")


def decode_event(data, cookie):
    if len(data) != EVENT.size:
        raise ValueError("truncated or unexpected DRM event length")
    kind, length, actual_cookie, timestamp, sequence = EVENT.unpack(data)
    if kind != 3 or length != EVENT.size or actual_cookie != cookie:
        raise ValueError("unexpected DRM event type, size or cookie")
    if timestamp <= 0:
        raise ValueError("invalid DRM timestamp")
    return timestamp, sequence


def summarize(first, last, requested_frames):
    elapsed_ns = last[0] - first[0]
    frames = last[1] - first[1]
    if elapsed_ns <= 0 or frames != requested_frames:
        raise ValueError("sequence/timestamp discontinuity; possible modeset")
    return {"frames": frames, "elapsed_ns": elapsed_ns,
            "sequence_hz": frames * 1_000_000_000 / elapsed_ns,
            "scope": "DRM sequence cadence, not compositor FPS"}


def queue(fd, crtc, sequence, cookie, relative=False):
    request = bytearray(struct.pack("=IIQQ", crtc, int(relative), sequence, cookie))
    try:
        fcntl.ioctl(fd, QUEUE_SEQUENCE, request)
    except OSError as error:
        raise OSError(error.errno, f"QUEUE_SEQUENCE cookie={cookie}: {error.strerror}") from error
    return struct.unpack("=IIQQ", request)[2]


def receive(fd, cookie, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
        raise TimeoutError("DRM sequence event deadline exceeded")
    return decode_event(os.read(fd, EVENT.size), cookie)


def measure(device, crtc, frames, timeout):
    fd = os.open(device, os.O_RDWR | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        deadline = time.monotonic() + timeout
        # Queue the end before receiving the start to retain vblank ownership.
        start = queue(fd, crtc, 2, 1, relative=True)
        queue(fd, crtc, start + frames, 2)
        first = receive(fd, 1, deadline)
        last = receive(fd, 2, deadline)
        return summarize(first, last, frames)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/dri/card0")
    parser.add_argument("--crtc", type=int, required=True)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    if not 0 < args.crtc < 2**32 or not 1 <= args.frames <= 600:
        parser.error("CRTC must be a positive u32; frames must be 1..600")
    if not 0 < args.timeout <= 30:
        parser.error("timeout must be greater than 0 and at most 30 seconds")
    try:
        print(json.dumps(measure(args.device, args.crtc, args.frames, args.timeout)))
    except (OSError, ValueError, TimeoutError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
