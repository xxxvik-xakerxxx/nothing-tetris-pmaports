#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Real C authentication/crypto, real RSA/hash callbacks, mocked allocation/SMC.
No secure transform is emulated as successful without actual matching plaintext.
"""
import ctypes as c
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest

so = sys.argv[1]
root = Path(os.environ["TETRIS_UBOOT_TREE"])
sys.argv = [sys.argv[0], so]
spec = importlib.util.spec_from_file_location("flat_scp_runtime",
    root / ".github/tests/test_tetris_scp_security_c.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
lib = base.library
lib.fixture_arena.restype = c.c_void_p
retain = lib.tetris_gpueb_flat_retain
retain.argtypes = [c.POINTER(base.Crypto), c.POINTER(base.Ops), c.c_void_p,
                  c.c_size_t, c.c_void_p, c.POINTER(c.c_void_p)]
lib.tetris_gpueb_flat_discard.argtypes = [c.c_void_p]
PIN = bytes.fromhex("e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e")


class NativeFlat(unittest.TestCase):
    def setUp(self):
        path = Path(os.environ["TETRIS_GPUEB_FACTORY_CONTAINER"])
        self.data = path.read_bytes()
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),
                         "58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22")
        self.input = c.create_string_buffer(self.data, len(self.data))
        self.raw_page = c.create_string_buffer(4096 + 63)
        self.page = (c.addressof(self.raw_page) + 63) & ~63
        self.calls = []
        self.plaintext = None
        self.result = c.c_void_p()
        lib.fixture_reset(0)
        self.arena = lib.fixture_arena()

        @base.Smc
        def smc(fn, a, b):
            self.calls.append((fn, a, b))
            if self.plaintext is None:
                return 9
            c.memmove(self.arena, self.plaintext, len(self.plaintext))
            return 0

        @base.Cache
        def cache(pointer, size):
            pass

        @base.CryptoHash
        def digest(pointer, size, output):
            c.memmove(output, hashlib.sha256(c.string_at(pointer, size)).digest(), 32)

        @base.Physical
        def physical(pointer):
            if pointer == self.page:
                return 0x48401000
            if self.arena <= pointer < self.arena + 0x100000:
                return 0x60000000 + pointer - self.arena
            return 0

        self.callbacks = (smc, cache, digest, physical)
        self.ops = base.CryptoOps(smc, cache, cache, digest, physical, 64)
        self.crypto = base.Crypto(c.pointer(self.ops), self.page, 1, 0)

    def call(self, pin=PIN):
        return retain(c.byref(self.crypto), c.byref(base.ops), self.input,
                      len(self.data), pin, c.byref(self.result))

    def test_public_factory_auth_reaches_mock_secure_failure_and_erases(self):
        self.assertNotEqual(self.call(), 0)
        self.assertEqual(self.calls, [(0xc2000133, 1, 0)])
        self.assertFalse(self.result.value)
        self.assertFalse(lib.fixture_claimed())
        self.assertEqual(c.string_at(self.arena, 0x100000), bytes(0x100000))

    def test_bad_pin_never_allocates_or_calls_secure(self):
        self.assertNotEqual(self.call(bytes(32)), 0)
        self.assertFalse(self.calls)
        self.assertFalse(lib.fixture_claimed())

    def test_ciphertext_tamper_rejected_before_allocate(self):
        self.input[512] = bytes([self.data[512] ^ 1])
        self.assertNotEqual(self.call(), 0)
        self.assertFalse(self.calls)
        self.assertFalse(lib.fixture_claimed())

    def test_allocation_and_mapping_faults(self):
        for fault in (1, 2):
            lib.fixture_reset(fault)
            self.assertNotEqual(self.call(), 0)
            self.assertFalse(self.calls)
            self.assertFalse(lib.fixture_claimed())

    def test_postdigest_mismatch_erases(self):
        self.plaintext = b"P" * 156064
        self.assertNotEqual(self.call(), 0)
        self.assertFalse(self.result.value)
        self.assertFalse(lib.fixture_claimed())
        self.assertEqual(c.string_at(self.arena, 0x100000), bytes(0x100000))

    @unittest.skipUnless(os.environ.get("TETRIS_GPUEB_PRIVATE_FACTORY_PLAIN"),
                         "success requires real privately verified factory plaintext")
    def test_retention_success_and_discard_failure(self):
        self.plaintext = Path(os.environ["TETRIS_GPUEB_PRIVATE_FACTORY_PLAIN"]).read_bytes()
        self.assertEqual(len(self.plaintext), 156064)
        self.assertEqual(hashlib.sha256(self.plaintext).hexdigest(),
                         "4cd3ac60605b30f92988a7606e95b7e4f82d70513bbd12923a0e562e9fc31702")
        self.assertEqual(self.call(), 0)
        self.assertTrue(self.result.value)
        self.assertEqual(c.string_at(self.arena, 156064), self.plaintext)
        lib.fixture_faults(4)
        self.assertNotEqual(lib.tetris_gpueb_flat_discard(self.result), 0)
        self.assertTrue(lib.fixture_claimed())
        self.assertEqual(c.string_at(self.arena, 0x100000), bytes(0x100000))
        lib.fixture_faults(0)
        self.assertEqual(lib.tetris_gpueb_flat_discard(self.result), 0)


if __name__ == "__main__":
    unittest.main()
