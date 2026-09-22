#!/usr/bin/env python3
"""Offline ABI fixtures; never opens a device."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "samples", Path(__file__).resolve().parents[1] / "check-live-sensor-samples.py")
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)


class SensorABI(unittest.TestCase):
    def test_layout(self):
        self.assertEqual(samples.PACKET_SIZE, 68)
        self.assertEqual(samples.INFO.size, 40)
        self.assertEqual(samples.EVENT.size, 76)
        self.assertEqual(samples.COMMAND.size, 52)

    def test_enable_disable(self):
        for enable in (False, True):
            cmd = samples.command(1, enable, 25)
            self.assertEqual(cmd[:4], bytes((1, int(enable), 16, 0)))
            self.assertEqual(struct.unpack_from("<qq", cmd, 4), (40_000_000, 0))
            self.assertEqual(cmd[20:], bytes(32))

    def test_vendor_zero_write_is_not_retried(self):
        with patch.object(samples.os, "write", return_value=0) as write:
            samples.control(123, 1, True, 25)
            write.assert_called_once()
        with patch.object(samples.os, "write", return_value=12):
            with self.assertRaises(OSError):
                samples.control(123, 1, True, 25)

    def test_ioctl(self):
        with patch.object(samples.fcntl, "ioctl") as ioctl:
            packet = samples.request(123, 6, 4)
            self.assertEqual(packet[0], 4)
            ioctl.assert_called_once_with(123, 0xc0446106, packet, True)

    def test_info(self):
        packet = bytearray(68)
        samples.INFO.pack_into(packet, 4, 1, 1000, b"icm4n607_acc", b"vendor")
        self.assertEqual(samples.info_decode(packet, 1)["name"], "icm4n607_acc")
        with self.assertRaises(ValueError):
            samples.info_decode(packet, 4)
        struct.pack_into("<I", packet, 8, 0)
        with self.assertRaises(ValueError):
            samples.info_decode(packet, 1)

    def test_samples_and_partial_records(self):
        event = samples.EVENT.pack(123456, 1, 3, 0, -1, 2, -3, *([0] * 13))
        decoded = list(samples.events_decode(event * 2))
        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0]["raw"][:3], [-1, 2, -3])
        self.assertEqual(decoded[0]["timestamp_ns"], 123456)
        with self.assertRaises(ValueError):
            list(samples.events_decode(event[:-1]))
        with self.assertRaises(ValueError):
            list(samples.events_decode(bytes(76)))


if __name__ == "__main__":
    unittest.main()
