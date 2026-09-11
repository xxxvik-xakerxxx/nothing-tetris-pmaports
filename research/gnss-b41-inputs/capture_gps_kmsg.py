"""Bounded, read-only GPS kernel-log capture; never opens a GPS device."""
import argparse
import base64
import json
import os
import select
import time


class CaptureError(RuntimeError):
    pass


class Records:
    def __init__(self, max_records=4096, max_scanned=65536):
        self.max_records = max_records
        self.max_scanned = max_scanned
        self.scanned = 0
        self.sequence = None
        self.records = []

    def feed(self, raw, receipt_ns):
        if not raw or len(raw) >= 8192 or self.scanned >= self.max_scanned:
            raise CaptureError("kernel record size or scan budget exceeded")
        header, separator, message = raw.partition(b";")
        fields = header.split(b",")
        if (not separator or len(fields) < 4 or
                not all(x.isdigit() for x in fields[:3])):
            raise CaptureError("malformed kernel header")
        priority, sequence, source_us = map(int, fields[:3])
        if priority > 191 or sequence >= 2**64 or source_us >= 2**64:
            raise CaptureError("kernel header outside bounds")
        if self.sequence is not None and sequence != self.sequence + 1:
            raise CaptureError("lost, duplicated or reordered kernel records")
        self.sequence = sequence
        self.scanned += 1
        if priority >> 3 or not message.startswith((b"GDL[", b"GDL-")):
            return
        if len(self.records) >= self.max_records:
            raise CaptureError("GPS record budget exceeded")
        self.records.append({
            "sequence": sequence,
            "source_us": source_us,
            "receipt_monotonic_ns": receipt_ns,
            "raw_base64": base64.b64encode(raw).decode("ascii"),
        })


def capture(duration, ready=None):
    if not 0 < duration <= 120:
        raise ValueError("capture duration must be in (0, 120] seconds")
    records = Records()
    result = {"ok": False, "error": None, "records": records.records,
              "scanned": 0, "last_sequence": None}
    fd = None
    try:
        fd = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        os.lseek(fd, 0, os.SEEK_END)
        start = time.monotonic_ns()
        result["start_monotonic_ns"] = start
        deadline = start + int(duration * 1_000_000_000)
        if ready is not None:
            ready()
        while time.monotonic_ns() < deadline:
            try:
                raw = os.read(fd, 8192)
            except BlockingIOError:
                remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
                if remaining > 0:
                    select.select([fd], [], [], remaining)
                continue
            records.feed(raw, time.monotonic_ns())
        result["ok"] = True
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        result["end_monotonic_ns"] = time.monotonic_ns()
        result["scanned"] = records.scanned
        result["last_sequence"] = records.sequence
        if fd is not None:
            try:
                os.close(fd)
            except OSError as error:
                result["ok"] = False
                result["cleanup_error"] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, required=True)
    args = parser.parse_args()
    result = capture(args.duration, ready=lambda: print("KMSG_CAPTURE_READY", flush=True))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
