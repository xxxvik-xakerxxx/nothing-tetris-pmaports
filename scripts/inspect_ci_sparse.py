"""Expand a hash-verified Android sparse ZIP member with bounded memory.

This creates an inspection copy only. Flash the original CI artifact, not this
derived file. Supports the fixed v1.0 header emitted by the CI img2simg tool.
"""
import argparse
import hashlib
import json
import os
import struct
import zipfile
import zlib


def expand(stream, target, expected_sha256, max_bytes):
    digest = hashlib.sha256()

    def read(size):
        data = bytearray()
        while len(data) < size:
            block = stream.read(size - len(data))
            if not block:
                raise ValueError("truncated sparse image")
            digest.update(block)
            data.extend(block)
        return bytes(data)

    header = struct.unpack("<IHHHHIIII", read(28))
    magic, major, minor, file_hdr, chunk_hdr, block_size, blocks, chunks, checksum = header
    if (magic != 0xED26FF3A or (major, minor, file_hdr, chunk_hdr) != (1, 0, 28, 12)
            or block_size != 4096 or not blocks or not 0 < chunks <= 1_000_000
            or not 0 < blocks * block_size <= max_bytes):
        raise ValueError("unsupported sparse header or output bound")
    written_blocks = 0
    crc = 0
    for _ in range(chunks):
        kind, reserved, count, total = struct.unpack("<HHII", read(12))
        length = count * block_size
        if reserved or total < 12 or written_blocks + count > blocks:
            raise ValueError("invalid chunk extent")
        if kind == 0xCAC4:
            if count or total != 16 or struct.unpack("<I", read(4))[0] != crc:
                raise ValueError("invalid sparse CRC chunk")
            continue
        if not count:
            raise ValueError("empty data chunk")
        if kind == 0xCAC1:
            if total != 12 + length:
                raise ValueError("invalid RAW chunk size")
            pattern = None
        elif kind == 0xCAC2:
            if total != 16:
                raise ValueError("invalid FILL chunk size")
            pattern = read(4) * (1024 * 1024 // 4)
        elif kind == 0xCAC3:
            if total != 12:
                raise ValueError("invalid DONT_CARE chunk size")
            pattern = bytes(1024 * 1024)
        else:
            raise ValueError("unknown sparse chunk type")
        remaining = length
        while remaining:
            size = min(remaining, 1024 * 1024)
            data = read(size) if pattern is None else pattern[:size]
            crc = zlib.crc32(data, crc)
            if kind == 0xCAC3:
                target.seek(size, os.SEEK_CUR)
            elif target.write(data) != len(data):
                raise ValueError("short output write")
            remaining -= size
        written_blocks += count
    if written_blocks != blocks or (checksum and checksum != crc):
        raise ValueError("block count or image CRC mismatch")
    if stream.read(1):
        raise ValueError("trailing sparse data")
    if digest.hexdigest() != expected_sha256:
        raise ValueError("CI sparse SHA256 mismatch")
    target.truncate(blocks * block_size)
    return {"source_sha256": digest.hexdigest(), "raw_bytes": blocks * block_size,
            "chunks": chunks, "crc32": crc}


def expand_archive(archive, entry, output, expected_sha256, max_bytes):
    with zipfile.ZipFile(archive) as package:
        matches = [info for info in package.infolist() if info.filename == entry]
        if len(matches) != 1 or matches[0].is_dir():
            raise ValueError("missing or duplicate ZIP member")
        # Exclusive creation also rejects symlinks and never replaces user data.
        with open(output, "xb") as target:
            try:
                with package.open(matches[0]) as stream:
                    return expand(stream, target, expected_sha256, max_bytes)
            except BaseException:
                os.unlink(output)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(expand_archive(args.archive, args.entry, args.output,
                                    args.sha256, args.max_bytes)))


if __name__ == "__main__":
    main()
