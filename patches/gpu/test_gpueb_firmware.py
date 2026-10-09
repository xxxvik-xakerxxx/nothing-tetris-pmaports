#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Synthetic GPUEB authentication/fault fixtures; no private firmware inputs."""
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import gpueb_firmware as fw


def der(tag, value):
    size = len(value)
    if size < 128:
        length = bytes((size,))
    else:
        encoded = size.to_bytes((size.bit_length() + 7) // 8, "big")
        length = bytes((128 | len(encoded),)) + encoded
    return bytes((tag,)) + length + value


def bitstring(value):
    return der(3, b"\0" + value)


class Firmware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "synthetic")])
        cert = x509.CertificateBuilder().subject_name(name).issuer_name(name) \
            .public_key(cls.root.public_key()).serial_number(1) \
            .not_valid_before(datetime.datetime(2026, 1, 1)) \
            .not_valid_after(datetime.datetime(2027, 1, 1)) \
            .sign(cls.root, hashes.SHA256())
        cls.template = fw.sequence(fw.sequence(cert.public_bytes(serialization.Encoding.DER))[0].encoded)
        cls.root_pin = hashlib.sha256(cls.spki(cls.root)).hexdigest()

    @staticmethod
    def spki(key):
        return key.public_key().public_bytes(serialization.Encoding.DER,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)

    def cert(self, key, fields, corrupt=False, algorithm=fw.PSS_EXPLICIT):
        body = [f.encoded for f in self.template[:7]]
        body[2] = fw.LEGACY_LABEL
        body[6] = self.spki(key)
        for (group, item), value in fields:
            body.extend((der(6, fw.OID_PREFIX + bytes((group, item))), value))
        tbs = der(0x30, b"".join(body))
        signature = key.sign(tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                             salt_length=32), hashes.SHA256())
        if corrupt:
            signature = signature[:-1] + bytes((signature[-1] ^ 1,))
        return der(0x30, tbs + algorithm + bitstring(signature))

    def container(self, mutation=None):
        image = bytearray()
        for index in (0, 3):
            payload = b"synthetic-rv33!!" * 16 if index == 0 else b"synthetic-auxiliary"
            header = self.header(index, len(payload))
            fields = [((2, 1), bitstring(hashlib.sha256(payload).digest() if index == 0 else b"d" * 32)),
                      ((2, 4), bitstring(hashlib.sha256(header).digest())),
                      ((2, 8), bitstring(b"w" * 32 if index == 0 else b"\0")),
                      ((4, 2), bitstring(b"p" * 32 if index == 0 else b"\0")),
                      ((2, 9), der(2, b"\x01\x00\x00" if index == 0 else b"\0"))]
            if mutation:
                mutation(index, fields)
            root = self.cert(self.root, [((1, 2), self.spki(self.leaf))])
            leaf = self.cert(self.leaf, fields)
            for i, data in enumerate((payload, root, leaf)):
                image.extend(header if i == 0 else self.header(index + i, len(data)))
                image.extend(data)
                image.extend(bytes((-len(image)) % 16))
        return image

    @staticmethod
    def header(index, size):
        h = bytearray(512)
        struct.pack_into("<II", h, 0, 0x58881688, size)
        h[8:40] = fw.NAMES[index].encode().ljust(32, b"\0")
        struct.pack_into("<8I", h, 48, 0x58891689, 512, 1,
                         (0, 0x02000000, 0x02000002)[index % 3],
                         int(index == 5), 16, 0,
                         0 if index % 3 == 0 else 0x22345678)
        return h

    def test_authenticated_program_not_boot_permission(self):
        report = fw.inspect(self.container(), self.root_pin)
        self.assertFalse(report["boot_permitted"])
        self.assertEqual(report["components"][0]["whole_payload_digest"], "verified")
        self.assertEqual(report["components"][1]["whole_payload_digest"], "unproven")
        self.assertEqual(report["trust"], "caller-pinned-root")
        self.assertEqual(report["components"][0]["signed_transform_word"], "0x10000")
        self.assertEqual(report["components"][0]["secure_transform_selector"], "unproven")

    def test_root_pin_mandatory_and_wrong_pin(self):
        for pin in (None, "", "g" * 64, "0" * 64):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                fw.inspect(self.container(), pin)

    def test_program_payload_and_signed_header_corruption(self):
        for offset in (512, 40, 80):
            data = self.container()
            data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                fw.inspect(data, self.root_pin)

    def test_signature_corruption(self):
        data = self.container()
        section = fw.sections(data)[2]
        data[section.offset + 512 + len(section.payload) - 1] ^= 1
        with self.assertRaises(InvalidSignature):
            fw.inspect(data, self.root_pin)

    def test_undelegated_key(self):
        data = self.cert(self.root, [((1, 2), self.spki(self.root))])
        self.assertNotEqual(fw.metadata(fw.certificate(data)[1], 1, 2).encoded,
                            self.spki(self.leaf))
        original = self.container()
        section = fw.sections(original)[1]
        self.assertEqual(len(data), len(section.payload))
        original[section.offset + 512:section.offset + 512 + len(data)] = data
        with self.assertRaisesRegex(ValueError, "not delegated"):
            fw.inspect(original, self.root_pin)

    def test_duplicate_missing_and_wrong_profile(self):
        def duplicate(index, fields):
            fields.append(fields[0])
        def missing(index, fields):
            fields.pop(1)
        def wrong(index, fields):
            fields[-1] = ((2, 9), der(2, b"\x01"))
        for mutate in (duplicate, missing, wrong):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                fw.inspect(self.container(mutate), self.root_pin)

    def test_layout_bounds_roles_and_padding(self):
        original = self.container()
        for size in (0, 511, 512, len(original) - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                fw.sections(original[:size])
        for offset in (0, 4, 8, 48, 52, 56, 60, 68, 72, 76):
            data = original.copy()
            data[offset] ^= 255
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                fw.sections(data)
        parts = fw.sections(original)
        end = parts[1].offset + 512 + len(parts[1].payload)
        data = original.copy()
        data[end] = 1
        with self.assertRaises(ValueError):
            fw.sections(data)
        self.assertEqual(len(fw.sections(original + bytes(256))), 6)
        for data in (original + b"unexpected", bytes(fw.MAX_IMAGE + 1)):
            with self.assertRaises(ValueError):
                fw.sections(data)

    def test_der_minimal_lengths_and_algorithm(self):
        for data in (b"\x30\x80\0\0", b"\x30\x81\0", b"\x30\x82\0\x80",
                     b"\x30\0extra", b"\x3f\0", b"\x30\x03\x03\x02\0"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fw.sequence(data)
        with self.assertRaises(ValueError):
            fw.certificate(self.cert(self.root, [], algorithm=fw.LEGACY_LABEL))

    def test_report_redacts_material(self):
        report = json.dumps(fw.inspect(self.container(), self.root_pin))
        for material in (b"w" * 32, b"p" * 32, b"synthetic-rv33!!"):
            self.assertNotIn(material.decode(), report)
            self.assertNotIn(material.hex(), report)

    def test_cli_read_only_and_failure_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.img"
            data = self.container()
            path.write_bytes(data)
            command = [sys.executable, str(Path(fw.__file__)), str(path),
                       "--expected-root-sha256", self.root_pin]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["boot_permitted"])
            result = subprocess.run(command[:-1] + ["0" * 64], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "GPUEB validation failed (ValueError)\n")
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(Path(tmp).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
