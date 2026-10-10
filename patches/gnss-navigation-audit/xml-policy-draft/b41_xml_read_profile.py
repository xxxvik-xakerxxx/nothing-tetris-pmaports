#!/usr/bin/env python3
"""Pinned B4.1 XML path/version producer; no loading, globals or filesystem writes."""
from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys

LIB_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
MNLD_SHA = "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83"
XML_SHA = "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31"
PRIMARY = "/vendor/etc/MNL_Config.xml"
PREFERRED = "/data/vendor/gps/MNL_Config.xml"
ROOT_CODES = (b"00", b"0O", b"0L", b"0S", b"0H", b"0V", b"AB")
LIB_SLICES = (
    (0x4fd044, 0x4fd070, "60e07ce0e6bca828f941a919422fe044d329240623cd3f66a1d9e81c4124c81e"),
    (0x4fc224, 0x4fc240, "6f2b21c832d2694f8184e66360e9f4d84dcc497fb814a7d7cd7f09acf5530d0f"),
    (0x4fcaf8, 0x4fcb0c, "1cf0db6a7a8f349fc90da854d1544bc70b858d69817a1f3537f15279c8a9fbd0"),
    (0x4fd20c, 0x4fd440, "39a32a4f610e341012176bbd0efabe0c30facf40b058dd1d36c34f4a839b1b75"),
    (0x4fd53c, 0x4fd604, "0c40151b230b4072504d48370073e9c64c58bd1e756489f6921e044b1fada5bc"),
    (0x500910, 0x500bbc, "855baf1bbcff12dc8fa33570781960e01ce942d8eb3ce09f1aa0875d33848b40"),
    (0x4ff8e4, 0x4ff998, "9dddc523108573c61fb327773c0c44e7fbc2fa6567d9278e189a108e2cb429c6"),
    (0x500450, 0x5004e4, "5d1ea4c1b2773d5ce8d64a63e44b2109cf9fd5fabdbffe508f4f39007ee44a2d"),
    (0x181e2, 0x181f1, "24f351ebfb33a287aa6196dee67bd9d3766fb70f9be61cef77aa54515c2f1fef"),
    (0x4c3df4, 0x4c3e00, "529a23bf326dc5e312f7cb46e58f40645b940dd5328a046da29d42b42d6b91f5"),
    (0x6eb0e8, 0x6eb101, "9b8844c374eac2c9375716923c73feb96d9d27f42b3d5ab629fef416b61cb11e"),
)
MNLD_SLICES = (
    (0x635e4, 0x6365c, "85c0d7f687630800d77707d422572cfef2afeacd16f97d556e9d39d790d5904e"),
    (0x88b78, 0x88b98, "84286e36a6c3bd8760f747b128041ca5438d880766e8e69b36f1384c790ceef2"),
    (0x88b98, 0x88bb8, "bd1d2623dec4ac32c3893f5f351c94e95e2929a6c44cee393bc4cb5e15b2b9ec"),
    (0x88ae0, 0x88b00, "bd1d2623dec4ac32c3893f5f351c94e95e2929a6c44cee393bc4cb5e15b2b9ec"),
)


class UnresolvedProfile(ValueError):
    """Outside the bounded, proven scanner subset; not OEM fopen failure."""


@dataclass(frozen=True)
class VersionScan:
    status: int
    compared_version: float
    root_version: str | None


@dataclass(frozen=True)
class ReadSelection:
    read_path: str
    write_path: str
    policy: int
    primary: VersionScan
    preferred: VersionScan


def scan_document(document):
    """Model only bounded source-backed lexical cases, not an XML validator.

    None denotes an observed fopen failure supplied by an owned file producer.
    It MUST NOT mean 'asset not included in a downloaded CI artifact'.
    """
    if document is None:
        return VersionScan(0, 0.0, None)
    if not isinstance(document, bytes) or len(document) > 1024 * 1024:
        raise UnresolvedProfile("bounded bytes input required")
    if b"\0" in document:
        raise UnresolvedProfile("embedded NUL / stdio-C-string mismatch")
    # OEM fgets is 1024 bytes, including terminator. Avoid modeling roots split
    # across chunks or its shared line/token counter exhaustion paths.
    chunks = document.split(b"\n")
    lines = [chunk + b"\n" for chunk in chunks[:-1]]
    if chunks[-1]:
        lines.append(chunks[-1])
    if len(lines) > 1024 or any(len(line) > 1023 for line in lines):
        raise UnresolvedProfile("fgets chunk/counter boundary not modeled")
    marker = b"<mnl_config version="
    for line_index, line in enumerate(lines):
        start = line.find(marker)
        if start < 0:
            continue
        end = line.find(b"type=")  # Actual strstr starts at the line, not root.
        if end < 0:
            return VersionScan(8, 0.0, None)
        raw = line[start + 21:end - 2]
        # Exact source extraction +0x15 and (type-marker delta)-0x17.
        match = re.search(rb'<mnl_config version="([^"]*)" type=', line)
        if match is None or match.start() != start or match.group(1) != raw:
            raise UnresolvedProfile("unsupported root quote/attribute layout")
        tokens = raw.split(b".")
        if (len(tokens) < 3 or len(tokens) > 127 or line_index + len(tokens) > 1023
                or any(not token for token in tokens)
                or not re.fullmatch(rb"[0-9]{1,15}", tokens[0])
                or len(tokens[2]) < 2):
            raise UnresolvedProfile("unproven atof/token/counter grammar")
        try:
            root_version = raw.decode("ascii")
        except UnicodeError as error:
            raise UnresolvedProfile("non-ASCII version") from error
        code = tokens[2][:2]
        return VersionScan(ROOT_CODES.index(code) + 1 if code in ROOT_CODES else 8,
                           float(tokens[0]), root_version)
    return VersionScan(8, 0.0, None)


def select_documents(primary, preferred):
    """Actual 4fd558..4fd5f0 arbitration, preserving nonzero status8."""
    first, second = scan_document(primary), scan_document(preferred)
    use_primary = second.status == 0 or (first.status != 0
                      and first.compared_version > second.compared_version)
    return ReadSelection(PRIMARY if use_primary else PREFERRED, PREFERRED,
                         7 if use_primary else 3, first, second)


def pinned_segments(path, digest):
    from elftools.elf.elffile import ELFFile
    path = Path(path)
    if not 0 < path.stat().st_size <= 16 * 1024 * 1024:
        raise ValueError("bounded ELF required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("wrong independently pinned ELF: " + str(path))
    with io.BytesIO(data) as stream:
        return [(segment["p_vaddr"], segment.data())
                for segment in ELFFile(stream).iter_segments()
                if segment["p_type"] == "PT_LOAD" and segment["p_filesz"]]


def elf_bytes(segments, address, length):
    for base, data in segments:
        if base <= address and address + length <= base + len(data):
            return data[address - base:address - base + length]
    raise ValueError("source bytes are not file-backed")


def validate_sources(lib, mnld, xml):
    library = pinned_segments(lib, LIB_SHA)
    producer = pinned_segments(mnld, MNLD_SHA)
    for segments, slices in ((library, LIB_SLICES), (producer, MNLD_SLICES)):
        for start, end, digest in slices:
            if hashlib.sha256(elf_bytes(segments, start, end - start)).hexdigest() != digest:
                raise ValueError(f"wrong source slice {start:#x}")
    for address, target in ((0x4fc22c, 0x4fd044), (0x4fc230, 0x4fd20c),
            (0x4fcaf8, 0x4fd044), (0x4fcafc, 0x4fd20c),
            (0x4fd06c, 0x6e48d0), (0x4fd544, 0x500910),
            (0x4fd554, 0x500910), (0x4fd600, 0x4ff868)):
        instruction = struct.unpack("<I", elf_bytes(library, address, 4))[0]
        relative = instruction & 0x3ffffff
        if relative & 0x2000000:
            relative -= 0x4000000
        if instruction & 0xfc000000 != 0x94000000 or address + relative * 4 != target:
            raise ValueError(f"wrong exact BL target {address:#x}")
    for address, expected in ((0x181e2, b"MNL_Config.xml\0"),
            (0x4c3df4, b"/vendor/etc/\0"), (0xca73, b".\0"),
            (0x11496, b"<mnl_config version=\0"), (0x174fc, b"type=\0"),
            (0x6eb0e8, b"NA\x0000\x000O\x000L\x000S\x000H\x000V\x00AB\x00")):
        if elf_bytes(library, address, len(expected)) != expected:
            raise ValueError(f"wrong reader literal {address:#x}")
    for address, expected in ((0x88b78, b"/vendor/etc/\0"),
            (0x88b98, b"/data/vendor/gps/\0"), (0x88ae0, b"/data/vendor/gps/\0")):
        if elf_bytes(producer, address, len(expected)) != expected:
            raise ValueError(f"wrong producer path {address:#x}")
    xml = Path(xml)
    if not 0 < xml.stat().st_size <= 65536:
        raise ValueError("bounded XML required")
    document = xml.read_bytes()
    if hashlib.sha256(document).hexdigest() != XML_SHA:
        raise ValueError("wrong independently pinned XML")
    return document


def source_profile(lib, mnld, xml):
    document = validate_sources(lib, mnld, xml)
    return {
        "schema": "b41-xml-read-profile-v1",
        "pins": {"libmnl": LIB_SHA, "mnld": MNLD_SHA, "xml": XML_SHA},
        "entry": {"caller": "0x4fc22c", "reset": "0x4fd044",
                  "selector": "0x4fd20c", "version_scanner": "0x500910",
                  "reader_call": "0x4fd600", "reader": "0x4ff868"},
        "paths": {"primary": PRIMARY, "preferred": PREFERRED, "write": PREFERRED,
                  "primary_directory_offset": "0x406", "preferred_directory_offset": "0x424",
                  "empty_preferred_fallback_offset": "0x208", "path_capacity": 50,
                  "filename": "MNL_Config.xml", "mnld_default_addresses":
                  {"primary": "0x88b78", "preferred": "0x88b98", "fallback": "0x88ae0"}},
        "version": {"delimiter": ".", "comparison_token": 0, "root_code_token": 2,
                    "comparison": "primary > preferred; ties retain preferred",
                    "status_zero": "fopen failed", "status_eight":
                    "nonzero, not proof of valid XML or GPS root",
                    "pinned_primary": asdict(scan_document(document))},
        "policy": {"preferred_selected": 3, "primary_selected": 7,
                   "failed_write_open": "policy &= ~4; reading and SET bit0 retained"},
        "readonly_exposure": {"path": PRIMARY, "sha256": XML_SHA,
             "requirement": "owned immutable private root; no source path reopen or stock overwrite",
             "data_path": "must derive existence/bytes from that root, never artifact omission"},
        "runtime_preferred_scan": None,
        "first_unresolved_runtime_branch": "actual owned preferred file fopen/status/version",
        "source_slices": {"libmnl": [[hex(a), hex(b), d] for a, b, d in LIB_SLICES],
                          "mnld": [[hex(a), hex(b), d] for a, b, d in MNLD_SLICES]},
        "execution_authority": "none: no native reader, SET, INIT, host readiness or writes",
    }


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: b41_xml_read_profile.py libmnl.so mnld MNL_Config.xml")
    print(json.dumps(source_profile(*sys.argv[1:]), indent=2, sort_keys=True))
