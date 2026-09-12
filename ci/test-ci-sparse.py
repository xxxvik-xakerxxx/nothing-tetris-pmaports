import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib

spec = importlib.util.spec_from_file_location("ci_sparse", Path(__file__).resolve().parents[1] /
                                             "scripts/inspect_ci_sparse.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def chunk(kind, blocks, data=b""):
    return struct.pack("<HHII", kind, 0, blocks, 12 + len(data)) + data


def sparse(chunks, blocks, checksum=0):
    return struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, 4096,
                       blocks, len(chunks), checksum) + b"".join(chunks)


class Tests(unittest.TestCase):
    def decode(self, data, digest=None, bound=1024 * 1024):
        with tempfile.TemporaryFile() as target:
            module.expand(io.BytesIO(data), target, digest or hashlib.sha256(data).hexdigest(), bound)
            target.seek(0)
            return target.read()

    def test_raw_fill_hole_crc(self):
        expected = b"A" * 4096 + b"abcd" * 1024 + bytes(4096)
        crc = zlib.crc32(expected)
        data = sparse([chunk(0xCAC1, 1, b"A" * 4096), chunk(0xCAC2, 1, b"abcd"),
                       chunk(0xCAC3, 1), chunk(0xCAC4, 0, struct.pack("<I", crc))], 3, crc)
        self.assertEqual(self.decode(data), expected)

    def test_large_hole_has_exact_extent(self):
        data = sparse([chunk(0xCAC3, 400)], 400)
        with tempfile.TemporaryFile() as target:
            module.expand(io.BytesIO(data), target, hashlib.sha256(data).hexdigest(), 2 * 1024 * 1024)
            self.assertEqual(target.seek(0, 2), 400 * 4096)
            target.seek(-1, 2)
            self.assertEqual(target.read(1), b"\0")

    def test_multiple_buffers(self):
        raw = b"a" * (300 * 4096)
        data = sparse([chunk(0xCAC1, 300, raw), chunk(0xCAC2, 400, b"bcde")], 700)
        self.assertEqual(self.decode(data, bound=4 * 1024 * 1024), raw + b"bcde" * (400 * 1024))

    def test_truncation_and_trailing_rejected(self):
        valid = sparse([chunk(0xCAC1, 1, b"A" * 4096)], 1)
        for data in (valid[:27], valid[:39], valid[:-1], valid + b"x"):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                self.decode(data)

    def test_hash_and_output_bound(self):
        data = sparse([chunk(0xCAC3, 1)], 1)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.decode(data, "0" * 64)
        with self.assertRaises(ValueError):
            self.decode(data, bound=4095)

    def test_bad_chunk_contracts(self):
        for value in (chunk(0xCAC1, 1, b"A"), chunk(0xCAC2, 1), chunk(0xCAC3, 1, b"x"),
                      chunk(0xCAC3, 2), chunk(0xCAC3, 0), chunk(0xABCD, 1),
                      chunk(0xCAC4, 1, bytes(4)), chunk(0xCAC4, 0, b"bad!")):
            with self.subTest(value=value[:12]), self.assertRaises(ValueError):
                self.decode(sparse([value], 1))

    def test_header_and_crc_rejected(self):
        valid = sparse([chunk(0xCAC3, 1)], 1)
        for offset in (0, 4, 6, 8, 10, 12, 16, 20, 24):
            bad = bytearray(valid)
            bad[offset] ^= 0x80
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.decode(bytes(bad))

    def test_zip_hash_failure_removes_only_new_output(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, output = Path(directory) / "image.zip", Path(directory) / "raw.img"
            data = sparse([chunk(0xCAC3, 1)], 1)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
                package.writestr("root.sparse", data)
            with self.assertRaises(ValueError):
                module.expand_archive(archive, "root.sparse", output, "0" * 64, 4096)
            self.assertFalse(output.exists())
            module.expand_archive(archive, "root.sparse", output, hashlib.sha256(data).hexdigest(), 4096)
            with self.assertRaises(FileExistsError):
                module.expand_archive(archive, "root.sparse", output, "0" * 64, 4096)
            self.assertEqual(output.stat().st_size, 4096)


if __name__ == "__main__":
    unittest.main()
