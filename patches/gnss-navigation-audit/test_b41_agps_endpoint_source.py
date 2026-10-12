#!/usr/bin/env python3
"""Static pinned ELF producer evidence; no emulator/native load/socket/device I/O."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock

MNLD_SHA = "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83"


class Image:
    def __init__(self, path):
        self.data = path.read_bytes()
        if hashlib.sha256(self.data).hexdigest() != MNLD_SHA:
            raise ValueError("wrong B4.1 mnld SHA256")
        if self.data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", self.data, 18)[0] != 183:
            raise ValueError("expected little-endian AArch64 ELF64")
        offset = struct.unpack_from("<Q", self.data, 32)[0]
        size, count = struct.unpack_from("<HH", self.data, 54)
        if size != 56 or offset + size * count > len(self.data):
            raise ValueError("invalid ELF program headers")
        self.loads = []
        for i in range(count):
            kind, flags, file_offset, address, _, file_size, _, _ = struct.unpack_from(
                "<II6Q", self.data, offset + i * size)
            if kind == 1:
                self.loads.append((address, file_size, file_offset, flags))

    def read(self, address, length):
        for base, size, offset, _ in self.loads:
            if base <= address and address + length <= base + size:
                return self.data[offset + address - base:offset + address - base + length]
        raise ValueError("unbacked ELF virtual address")

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def string(self, address):
        return self.read(address, 128).split(b"\0", 1)[0]

    def call(self, address):
        instruction = self.word(address)
        if instruction >> 26 != 0b100101:
            raise ValueError("not AArch64 BL")
        immediate = instruction & ((1 << 26) - 1)
        if immediate & (1 << 25):
            immediate -= 1 << 26
        return address + immediate * 4


class EndpointSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = Image(INPUT)

    def test_exact_literals_and_addresses(self):
        image = self.image
        path = image.string(0x20a20)
        self.assertEqual(path, b"/data/agps_supl/mnl_to_agps")
        # Stock tests an immutable literal, but sends through writable path88068.
        self.assertEqual(image.string(0x88068), path)
        name = image.string(0x20a3c)
        self.assertEqual(name, b"mtk_mnl2agps")
        # Actual constructor takes first8 literal bytes, then MOV/MOVK 'agps'.
        self.assertEqual(image.word(0x38178), 0x528cec28)
        self.assertEqual(image.word(0x3817c), 0x72ae6e08)
        tail = struct.pack("<I", 0x73706761)
        self.assertEqual(image.read(0x20a3c, 8) + tail, name)
        self.assertEqual(image.word(0x3818c), 0xb800b3e8)  # STUR W8 at sp+b
        self.assertEqual(image.word(0x381ac), 0xf80033e8)  # STUR X8 at sp+3
        self.assertEqual(image.word(0x381c0), 0x528001e2)  # connect length15
        self.assertEqual(len(b"\1\0\0" + name), 15)  # NO name terminator
        self.assertEqual(image.word(0x383f8), 0x11000c18)  # pathname strlen+3
        self.assertEqual(len(b"\1\0" + path + b"\0"), len(path) + 3)

    def test_wrong_asset_is_refused_before_parsing(self):
        wrong = Mock()
        wrong.read_bytes.return_value = b"not the pinned mnld"
        with self.assertRaisesRegex(ValueError, "wrong B4.1 mnld SHA256"):
            Image(wrong)

    def test_source_route_and_socket_contract(self):
        image = self.image
        expected = {
            0x380d4: 0x10f44a60,  # ADR X0 stat literal20a20
            0x380f4: 0x3100041f,  # stat==-1 -> abstract branch3815c
            0x380f8: 0x54000320,
            0x38100: 0x12140d08,  # mode & S_IFMT
            0x38104: 0x7140111f,  # S_IFDIR -> abstract; other types -> filesystem
            0x38108: 0x540002a0,
            0x3810c: 0x52800020,  # AF_UNIX
            0x38110: 0x52800041,  # SOCK_DGRAM
            0x38164: 0x6f00e400,  # zero-fill abstract address
            0x38168: 0x52800041,
            0x38180: 0x39000bff,  # abstract NUL at byte2
            0x38194: 0x9128f108,  # literal20a3c
            0x381f0: 0x32150082,  # O_NONBLOCK after connect
            0x383ac: 0x1027e5e1,  # ADR X1 writable filesystem path88068
            0x383ec: 0x790003e8,  # family at byte0
        }
        for address, instruction in expected.items():
            with self.subTest(address=hex(address)):
                self.assertEqual(image.word(address), instruction)
        self.assertEqual(image.call(0x380f0), 0x85400)  # stat PLT
        self.assertEqual(image.call(0x38118), 0x85350)  # socket PLT
        self.assertEqual(image.call(0x381b0), 0x85350)
        self.assertEqual(image.call(0x381c8), 0x854f0)  # connect PLT
        self.assertEqual(image.call(0x38418), 0x853b0)  # filesystem sendto PLT
        self.assertEqual(image.call(0x382f8), 0x85380)  # failed connect closes fd
        self.assertEqual(image.call(0x3853c), 0x85380)  # send branch cleanup

    def test_actual_frame_packet_senders_reach_this_route(self):
        self.assertEqual(self.image.call(0x39508), 0x380a0)  # type150
        self.assertEqual(self.image.call(0x3959c), 0x380a0)  # type152
        self.assertEqual(self.image.word(0x394e4), 0x528012c2)
        self.assertEqual(self.image.word(0x3958c), 0x52801302)

    def test_ci_runner_keeps_native_execution_gated(self):
        here = Path(__file__).resolve().parent
        source = (here / "b41_agps_endpoint.c").read_text()
        runner = (here / "run_agps_host_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertIn('"$directory/test_b41_agps_endpoint.c"', runner)
        self.assertIn('20 "$temporary/test-agps-endpoint"', runner)
        for syscall in ("lstat", "socket", "connect", "close", "getsockopt", "getpeername", "fstat"):
            self.assertIn(f"--wrap={syscall}", runner)
        self.assertIn("SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC", source)
        self.assertIn("b41_agps_owner_take", source)
        self.assertNotIn("missing_contracts", source)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_b41_agps_endpoint_source.py PINNED_MNLD")
    INPUT = Path(sys.argv.pop())
    unittest.main()
