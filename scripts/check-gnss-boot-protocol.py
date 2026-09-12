#!/usr/bin/env python3
"""Validate the bounded MT6878 GNSS primary boot framing model.

This is a host-only protocol gate. It must not access gpsdl devices, submit
firmware fragments, start gpsd/geoclue or imply a position fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
import struct
import unittest


MAX_CHUNK = 512
MAX_BODY = 508


def encode_frame(command: int, payload: bytes) -> bytes:
    if not 0 <= command <= 0xFFFF:
        raise ValueError("command outside boot transport bounds")
    if not 1 <= len(payload) <= MAX_BODY - 6:
        raise ValueError("payload outside boot transport bounds")
    body = struct.pack("<HH", len(payload) + 4, command) + payload
    body += struct.pack("<H", sum(body) & 0xFFFF)
    escaped = body.replace(b"\xde", b"\xde\xe0").replace(b"\xaa", b"\xde\xdf")
    return b"\xaa\xf0" + escaped + b"\xaa\x0f"


class BootFrameDecoder:
    def __init__(self) -> None:
        self._state = "search"
        self._body = bytearray()
        self._failed = False

    def _fail(self, reason: str) -> None:
        self._body.clear()
        self._failed = True
        raise ValueError(reason)

    def feed(self, chunk: bytes) -> list[bytes]:
        if self._failed:
            raise RuntimeError("discard failed decoder")
        if len(chunk) > MAX_CHUNK:
            self._fail("read chunk exceeds 512 bytes")
        frames = []
        for byte in chunk:
            if self._state == "search":
                if byte == 0xAA:
                    self._state = "prefix"
                continue
            if self._state == "prefix":
                if byte == 0xF0:
                    self._state = "body"
                elif byte != 0xAA:
                    self._state = "search"
                continue
            if self._state == "escape":
                if byte not in (0xDF, 0xE0):
                    self._fail("invalid escape")
                self._body.append(0xAA if byte == 0xDF else 0xDE)
                self._state = "body"
            elif self._state == "suffix":
                if byte != 0x0F:
                    self._fail("invalid or nested frame delimiter")
                if len(self._body) < 7:
                    self._fail("short frame body")
                frames.append(bytes(self._body))
                self._body.clear()
                self._state = "search"
            elif byte == 0xDE:
                self._state = "escape"
            elif byte == 0xAA:
                self._state = "suffix"
            else:
                self._body.append(byte)
            if len(self._body) > MAX_BODY:
                self._fail("frame exceeds receive ring capacity")
        return frames


class Phase(Enum):
    BOOT_INFO = auto()
    FRAGMENT = auto()
    COMPLETE = auto()


@dataclass(frozen=True)
class BootAck:
    command: int
    index: int
    payload: bytes


def decode_boot_ack(body: bytes) -> BootAck | None:
    if len(body) < 7:
        raise ValueError("short frame")
    length, command = struct.unpack_from("<HH", body)
    if (length & 0xFFF) != len(body) - 2:
        raise ValueError("frame length mismatch")
    checksum = struct.unpack_from("<H", body, len(body) - 2)[0]
    if sum(body[:-2]) & 0xFFFF != checksum:
        raise ValueError("frame checksum mismatch")
    expected_sizes = {0xFE31: 10, 0xFE32: 2}
    if command not in expected_sizes:
        return None
    payload = bytes(body[4:-2])
    if len(payload) != expected_sizes[command]:
        raise ValueError("unexpected boot acknowledgement size")
    return BootAck(command, struct.unpack_from("<H", payload)[0], payload)


class BootExchange:
    def __init__(self, fragment_count: int) -> None:
        if not 1 <= fragment_count <= 256:
            raise ValueError("invalid fragment count")
        self.fragment_count = fragment_count
        self.phase = Phase.BOOT_INFO
        self.index = 0
        self.pending = False

    def mark_submitted(self) -> None:
        if self.pending or self.phase is Phase.COMPLETE:
            raise RuntimeError("no request available for submission")
        self.pending = True

    def accept(self, body: bytes) -> bool:
        ack = decode_boot_ack(body)
        expected = 0xFE31 if self.phase is Phase.BOOT_INFO else 0xFE32
        if (
            not self.pending
            or ack is None
            or ack.command != expected
            or ack.index != self.index
        ):
            return False
        self.pending = False
        if self.phase is Phase.BOOT_INFO:
            self.phase = Phase.FRAGMENT
            self.index = 1
        elif self.index == self.fragment_count:
            self.phase = Phase.COMPLETE
        else:
            self.index += 1
        return True

    def driver_fragment_index(self) -> int:
        if self.phase is not Phase.FRAGMENT or self.pending:
            raise RuntimeError("no fragment available for submission")
        return self.index - 1


def ack_body(command: int, index: int, size: int | None = None) -> bytes:
    if size is None:
        size = 10 if command == 0xFE31 else 2
    payload = (struct.pack("<H", index) + bytes(10))[:size]
    body = struct.pack("<HH", len(payload) + 4, command) + payload
    return body + struct.pack("<H", sum(body) & 0xFFFF)


class GnssBootProtocolTests(unittest.TestCase):
    def test_known_vendor_version_request(self) -> None:
        self.assertEqual(
            encode_frame(0xFE08, b"\x18\x00").hex(),
            "aaf0060008fe18002401aa0f",
        )

    def test_every_split_and_escaped_bytes(self) -> None:
        wire = encode_frame(0xFE31, b"\x00\x00\xaa\xde" + bytes(6))
        for split in range(len(wire) + 1):
            decoder = BootFrameDecoder()
            bodies = decoder.feed(wire[:split]) + decoder.feed(wire[split:])
            self.assertEqual(len(bodies), 1)
            state = BootExchange(1)
            state.mark_submitted()
            self.assertTrue(state.accept(bodies[0]))
            self.assertEqual(state.phase, Phase.FRAGMENT)

    def test_bytewise_complete_exchange(self) -> None:
        decoder = BootFrameDecoder()
        state = BootExchange(106)
        for index in range(107):
            payload = index.to_bytes(2, "little")
            if index == 0:
                payload += bytes(8)
            state.mark_submitted()
            wire = encode_frame(0xFE31 if index == 0 else 0xFE32, payload)
            bodies = []
            for byte in wire:
                bodies.extend(decoder.feed(bytes([byte])))
            self.assertEqual(len(bodies), 1)
            self.assertTrue(state.accept(bodies[0]))
        self.assertEqual(state.phase, Phase.COMPLETE)

    def test_complete_exchange_sizes(self) -> None:
        for count in (1, 106, 256):
            state = BootExchange(count)
            state.mark_submitted()
            self.assertTrue(state.accept(ack_body(0xFE31, 0)))
            for index in range(1, count + 1):
                self.assertEqual(state.driver_fragment_index(), index - 1)
                state.mark_submitted()
                self.assertTrue(state.accept(ack_body(0xFE32, index)))
            self.assertEqual(state.phase, Phase.COMPLETE)

    def test_mismatch_and_unsolicited_do_not_advance(self) -> None:
        state = BootExchange(106)
        self.assertFalse(state.accept(ack_body(0xFE31, 0)))
        state.mark_submitted()
        for command, index in ((0xFE32, 0), (0xFE31, 1), (0xFE14, 0)):
            self.assertFalse(state.accept(ack_body(command, index)))
            self.assertEqual(
                (state.phase, state.index, state.pending),
                (Phase.BOOT_INFO, 0, True),
            )

    def test_corruption_does_not_advance(self) -> None:
        good = ack_body(0xFE31, 0)
        state = BootExchange(106)
        state.mark_submitted()
        for offset in range(len(good)):
            bad = bytearray(good)
            bad[offset] ^= 1
            with self.assertRaises(ValueError):
                state.accept(bytes(bad))
            self.assertEqual(
                (state.phase, state.index, state.pending),
                (Phase.BOOT_INFO, 0, True),
            )

    def test_ack_sizes(self) -> None:
        for command, expected in ((0xFE31, 10), (0xFE32, 2)):
            for size in range(12):
                if size == expected:
                    self.assertEqual(decode_boot_ack(ack_body(command, 0, size)).index, 0)
                else:
                    with self.assertRaises(ValueError):
                        decode_boot_ack(ack_body(command, 0, size))

    def test_decoder_failure_is_terminal(self) -> None:
        for wire in (
            b"\xaa\xf0\xde\x00",
            b"\xaa\xf0\xaa\xf0",
            b"\xaa\xf0\xaa\x0f",
            bytes(513),
        ):
            decoder = BootFrameDecoder()
            with self.assertRaises(ValueError):
                decoder.feed(wire)
            with self.assertRaises(RuntimeError):
                decoder.feed(encode_frame(0xFE32, b"\x01\x00"))
        decoder = BootFrameDecoder()
        self.assertEqual(decoder.feed(b"\xaa\xf0" + bytes(508)), [])
        with self.assertRaises(ValueError):
            decoder.feed(b"\x00")

    def test_truncation_does_not_complete(self) -> None:
        wire = encode_frame(0xFE32, b"\x01\x00")
        for length in range(len(wire)):
            self.assertEqual(BootFrameDecoder().feed(wire[:length]), [])

    def test_submission_guards(self) -> None:
        for count in (0, -1, 257):
            with self.assertRaises(ValueError):
                BootExchange(count)
        state = BootExchange(1)
        with self.assertRaises(RuntimeError):
            state.driver_fragment_index()
        state.mark_submitted()
        with self.assertRaises(RuntimeError):
            state.mark_submitted()


if __name__ == "__main__":
    unittest.main()
