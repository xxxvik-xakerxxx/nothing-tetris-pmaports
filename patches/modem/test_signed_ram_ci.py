#!/usr/bin/env python3
"""CI-only real RSA-PSS signed-byte tests; synthetic keys are never port trust."""
import os
if os.environ.get("CI") != "true":
    raise SystemExit("Crypto fixture execution is CI-only")

import struct
import unittest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import verify_modem_signed_ram as v


def der(tag, payload):
    n = len(payload)
    length = bytes([n]) if n < 128 else bytes([0x82, n >> 8, n & 255]) if n >= 256 else bytes([0x81, n])
    return bytes([tag]) + length + payload


def certificate(private, spki, metadata, *, salt_length=32):
    body = [der(2, b"\1"), der(2, b"\1"), v.LEGACY,
            der(0x30, b""), der(0x30, b""), der(0x30, b""), spki]
    for group, item, value in metadata:
        body.extend([v.OID_PREFIX + bytes((group, item)), value])
    tbs = der(0x30, b"".join(body))
    signature = private.sign(tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=salt_length),
                             hashes.SHA256())
    return der(0x30, tbs + v.PSS + der(3, b"\0" + signature))


def member_header(name, payload):
    h = bytearray(512)
    for offset, value in ((0, 0x58881688), (4, len(payload)), (48, 0x58891689),
                          (52, 512), (68, 16)):
        struct.pack_into("<I", h, offset, value)
    h[8:8 + len(name)] = name
    return bytes(h)


def packed(name, payload):
    result = member_header(name, payload) + payload
    return result + b"\0" * (-len(result) % 16)


class SignedRam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.root_spki = cls.root.public_key().public_bytes(serialization.Encoding.DER,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.leaf_spki = cls.leaf.public_key().public_bytes(serialization.Encoding.DER,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.pin = v.digest(cls.root_spki)
        cls.cert1 = certificate(cls.root, cls.root_spki, [(1, 2, cls.leaf_spki)])
        rom = bytearray(1024)
        rom[-512:-500] = b"CHECK_HEADER"
        rom[-512 + 168] = 1
        for offset, value in ((12, 6), (16, 2), (20, 14), (172, 4096), (176, 768),
                              (184, 2048), (188, 512), (192, 1), (196, 0), (200, 4096),
                              (0x190, 3), (508, 512)):
            struct.pack_into("<I", rom, 512 + offset, value)
        cls.rom, cls.dsp, cls.drdi = bytes(rom), bytes(range(16)), b"r" * 16

    def bundle(self, *, transformed=False):
        result = b""
        for name, payload in ((b"md1rom", self.rom), (b"md1drdi", self.drdi), (b"md1dsp", self.dsp)):
            metadata = [(2, 4, der(3, b"\0" + v.digest(member_header(name, payload)))),
                        (2, 1, der(3, b"\0" + v.digest(payload))),
                        (2, 6, der(3, b"\0" + (b"\1" if transformed else b"\0"))),
                        (2, 8, der(3, b"\0\0")), (4, 2, der(3, b"\0\0"))]
            cert2 = certificate(self.leaf, self.leaf_spki, metadata)
            result += packed(name, payload) + packed(b"cert1md" if name == b"md1rom" else b"cert1", self.cert1)
            result += packed(b"cert2", cert2)
        return result

    def verify(self, data, rom=None, dsp=None, **kwargs):
        return v.verify_signed_placement(data, self.rom if rom is None else rom,
                                         self.dsp if dsp is None else dsp,
                                         kwargs.pop("reservation_size", 4096),
                                         trusted_pin=kwargs.pop("pin", self.pin), **kwargs)

    def test_real_pss_and_full_signed_extent(self):
        plan = self.verify(self.bundle())
        self.assertEqual((plan.rom_size, plan.logical_image_size, plan.dsp_offset), (1024, 768, 2048))
        self.assertEqual(plan.rom_sha256, v.digest(self.rom).hex())

    def test_changed_installed_rom_or_dsp(self):
        data = self.bundle()
        with self.assertRaisesRegex(v.Rejected, "installed ROM"):
            self.verify(data, rom=b"!" + self.rom[1:])
        with self.assertRaisesRegex(v.Rejected, "installed DSP"):
            self.verify(data, dsp=b"!" + self.dsp[1:])

    def test_logical_size_is_not_signed_extent(self):
        with self.assertRaisesRegex(v.Rejected, "span lengths"):
            self.verify(self.bundle(), rom=self.rom[:768])

    def test_modified_payload_even_with_matching_snapshot(self):
        data = bytearray(self.bundle())
        data[512] ^= 1
        with self.assertRaisesRegex(v.Rejected, "signed non-transformed payload"):
            self.verify(bytes(data), rom=bytes(data[512:1536]))

    def test_modified_signed_member_header(self):
        data = bytearray(self.bundle())
        data[100] ^= 1
        with self.assertRaisesRegex(v.Rejected, "signed 512-byte"):
            self.verify(bytes(data))

    def test_root_pin_cannot_come_from_chosen(self):
        with self.assertRaisesRegex(v.Rejected, "root SPKI pin"):
            self.verify(self.bundle(), pin=v.ROOT_PIN)

    def test_bad_signature(self):
        data = self.bundle()
        changed = bytearray(self.cert1)
        changed[-1] ^= 1
        with self.assertRaisesRegex(v.Rejected, "certificate signature"):
            self.verify(data.replace(self.cert1, bytes(changed)))

    def test_nontransform_profile_only(self):
        with self.assertRaisesRegex(v.Rejected, "non-transform"):
            self.verify(self.bundle(transformed=True))

    def test_wrong_delegation_despite_valid_root_signature(self):
        wrong = certificate(self.root, self.root_spki, [(1, 2, self.root_spki)])
        with self.assertRaisesRegex(v.Rejected, "root delegation"):
            self.verify(self.bundle().replace(self.cert1, wrong))

    def test_signature_salt_not_auto_detected(self):
        wrong = certificate(self.root, self.root_spki, [(1, 2, self.leaf_spki)], salt_length=64)
        with self.assertRaisesRegex(v.Rejected, "certificate signature"):
            self.verify(self.bundle().replace(self.cert1, wrong))

    def test_small_reservation(self):
        with self.assertRaisesRegex(v.Rejected, "layout bounds"):
            self.verify(self.bundle(), reservation_size=4095)

    def test_unsigned_trailing_bytes_are_not_a_window_digest(self):
        self.assertEqual(self.verify(self.bundle()), self.verify(self.bundle() + b"unsigned-tail"))

    def test_der_bounds(self):
        for data in (b"", b"\x30\x80\0\0", b"\x30\x81\x01\0", b"\x30\x82\0\x80" + bytes(128)):
            with self.assertRaises(v.Rejected):
                v.parse_certificate(data)


if __name__ == "__main__":
    unittest.main()
