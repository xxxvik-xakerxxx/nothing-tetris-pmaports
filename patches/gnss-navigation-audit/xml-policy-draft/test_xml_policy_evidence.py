#!/usr/bin/env python3
"""Read-only exact instruction/XML checks; no emulator, C build or ELF loading."""
import ast
import hashlib
import io
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
LIB_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
XML_SHA = "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31"
LIB = XML = LIB_PATH = XML_PATH = None
SLICES = (
    (0x4fd044, 0x4fd070, "60e07ce0e6bca828f941a919422fe044d329240623cd3f66a1d9e81c4124c81e"),
    (0x4fc224, 0x4fc240, "6f2b21c832d2694f8184e66360e9f4d84dcc497fb814a7d7cd7f09acf5530d0f"),
    (0x4fcaf8, 0x4fcb0c, "1cf0db6a7a8f349fc90da854d1544bc70b858d69817a1f3537f15279c8a9fbd0"),
    (0x4fd238, 0x4fd24c, "cb1233aa9c92b34860dcabb893c8cd7547328f79f1e83ed881f6c859f5cb7dbd"),
    (0x4fd53c, 0x4fd604, "0c40151b230b4072504d48370073e9c64c58bd1e756489f6921e044b1fada5bc"),
    (0x500194, 0x5001ac, "ab398ec8f9ed9388c993bcb462dbf07cf4f580a3ef50e8cfe6dd6678fb4dec93"),
    (0x4fe320, 0x4fe4b8, "ad0467198b401bf6356cf240d876012528f1715375899f070e610ddf26710728"),
    (0x50c224, 0x50c248, "8783a8d75fef07a4e49791eaaa6e83ced0ebd58e09d727c3e7561020b565a899"),
    (0x50c130, 0x50c1d8, "4c1282be31bf8bbedc98808e35f5773e8c1c18748a58628e71db3279a83b627b"),
    (0x4fe8f4, 0x4fe984, "5a15609c8815c093e0101f30087857dcce11db347cf2547182410286eee52e82"),
    (0x4fecfc, 0x4fed64, "a67848db039bc2e3993e1e94b95d092de930154a7ed217df08c1de84da8364f2"),
    (0x4ff194, 0x4ff1d4, "e317bd3a39256cd5387274fb590cfc908dbcf849aa733fb5cb54f6496545991d"),
    (0x4ff510, 0x4ff560, "60111f1144cf9d4a7cfa0ff8542bbb0c067a75ab6d687830af3e102a307a9551"),
    (0x4fd9c4, 0x4fda40, "fb4b27e0653e13a597e885c3a9c6680e537d9fb5d5fca1b67dc747fcd06947fd"),
    (0x4fda40, 0x4fda68, "c0935b47d7e09e1aeec131842dfdff9af1531bba2e9a909a8177302d49cecba0"),
    (0x4fdc98, 0x4fdccc, "64de075c690ce9ec4ec0e56baa338bb765753a72fd82eea8d01be8ca3e119947"),
    (0x4fe6b4, 0x4fe6ec, "11ca834892c819dec5d84555d1f09b24923dd46bb7a4a21df38a95490dd81a00"),
    (0x4fe9cc, 0x4fe9fc, "1dbfb2904e9890df40308f58415cfc63c9091014da396b6e400a24aea2e4d35f"),
    (0x4ff200, 0x4ff244, "8333453af8fc79d5d15505b8ef826b51edf5441464d1ee0707555ff278aa43a1"),
    (0x4feb38, 0x4febbc, "79318f2a6e8b170b5e837d01c5c429d98c6c8df6bf8d28b50e56cf9eb62525fe"),
    (0x4fed64, 0x4fedd0, "563bfb3f976ff61ca737e42b184939e385ff034d9a81a8526dbf8dbf26761d1e"),
    (0x4fec70, 0x4fecd8, "60c6e7ddba5570c62c5ef34aa74d85779cfdf4b1e15975c1bb1607d2d5a5e47b"),
    (0x4ff56c, 0x4ff5b8, "e3a27e4d96157078923c300bb6c2d7141b347552cab631e57b4a0ea8386a1698"),
    (0x4ff71c, 0x4ff734, "480ae16ec6ab6f64af2d16d8d76a70721e89728b7704394e79249b6461156f0e"),
    (0x508cfc, 0x508d00, "c5e7c7cf140314007a1ad74a653870bb3acd61cf015afc8f69a21c9fb4d2807d"),
)


def pinned(path, digest, limit):
    if not 0 < path.stat().st_size <= limit:
        raise ValueError("bounded asset required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("independent full asset pin mismatch")
    return data


def at(address, size):
    for s in ELFFile(io.BytesIO(LIB)).iter_segments():
        if s["p_type"] == "PT_LOAD" and s["p_vaddr"] <= address and address + size <= s["p_vaddr"] + s["p_filesz"]:
            offset = s["p_offset"] + address - s["p_vaddr"]
            return LIB[offset:offset + size]
    raise ValueError("file-backed range required")


def target(address, opcode=0x94000000):
    word = struct.unpack("<I", at(address, 4))[0]
    if word & 0xfc000000 != opcode:
        raise ValueError("unexpected direct branch opcode")
    relative = word & 0x3ffffff
    if relative & 0x2000000:
        relative -= 0x4000000
    return address + relative * 4


class EvidenceTests(unittest.TestCase):
    def test_set_oracle_source_admission_before_iteration(self):
        from test_b41_xml_set_tail_oracle import load_stock
        self.assertEqual(len(load_stock(LIB_PATH, XML_PATH)), 15)
        with tempfile.TemporaryDirectory() as temporary:
            empty = Path(temporary) / "MNL_Config.xml"
            empty.write_bytes(b'<mnl_config version="21111601.6.00.00" type="gps"/>')
            with self.assertRaisesRegex(ValueError, "pinned stock XML"):
                load_stock(LIB_PATH, empty)

    def test_exact_slices(self):
        for start, end, digest in SLICES:
            self.assertEqual(hashlib.sha256(at(start, end - start)).hexdigest(), digest, hex(start))

    def test_reset_reader_set_dispatch_order(self):
        self.assertEqual(struct.unpack("<Q", at(0x6e6660, 8))[0], 0x7178b8)
        self.assertEqual(struct.unpack("<I", at(0x4fd068, 4))[0], 0x52807f02)  # mov w2,#3f8.
        self.assertEqual(target(0x4fd06c), 0x6e48d0)  # memset globals, not XML text.
        self.assertEqual(target(0x4fc22c), 0x4fd044)
        self.assertEqual(target(0x4fc230), 0x4fd20c)
        self.assertEqual(target(0x4fd600), 0x4ff868)
        self.assertEqual(target(0x500378), 0x4fd870)
        self.assertEqual(target(0x4fe430), 0x50c130)
        self.assertEqual(target(0x4fe46c), 0x50c1d8)
        self.assertEqual(target(0x50c240), 0x508cfc)
        self.assertEqual(target(0x508cfc, 0x14000000), 0x5243a0)

    def test_exact_format_strings_and_epsilon(self):
        for address, text in ((0x13e75, b"XML:%s,v%.2f,Cfg"), (0x16711, b",%f"),
                              (0x22932, b",%.0f"), (0xf988, b"$%s*%02X\r\n")):
            self.assertEqual(at(address, len(text) + 1), text + b"\0")
        self.assertEqual(struct.unpack("<d", at(0xa1e0, 8))[0], 1e-8)

    def test_recipe_table_matches_enabled_xml(self):
        source = (HERE / "b41_xml_set_tail.c").read_text()
        recipes = re.findall(r'\{"([^"]+)", (\d+), ([01]), ([01]), ([01])\}', source)
        actual = {name: (int(version), int(integer), int(sparse), int(counted))
                  for name, version, integer, sparse, counted in recipes}
        nodes = [n for n in ET.fromstring(XML).findall("feature") if n.findtext("config") == "1"]
        self.assertEqual(len(actual), 15)
        self.assertEqual(set(actual), {n.text.strip() for n in nodes})
        for n in nodes:
            name = n.text.strip()
            self.assertEqual(actual[name][0], float(n.findtext("version")))
            expected = (0, 1, 0) if name == "DCB" else (0, 0, 1) if name in ("IFB", "GGTO", "GNSSPower") else (1, 0, 1)
            self.assertEqual(actual[name][1:], expected)
        self.assertNotIn("xml_policy_missing = 0", source)
        self.assertNotIn("property_get", source)

    def test_offline_runner_and_oracle_admission(self):
        subprocess.run(["sh", "-n", str(HERE / "run_xml_set_tail_ci.sh")], check=True, timeout=5)
        env = dict(os.environ, CI="false", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(["sh", str(HERE / "run_xml_set_tail_ci.sh")], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("CI-only", result.stderr)
        oracle = HERE / "test_b41_xml_set_tail_oracle.py"
        ast.parse(oracle.read_text())
        result = subprocess.run([sys.executable, str(oracle)], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linux CI-only", result.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_xml_policy_evidence.py libmnl.so MNL_Config.xml")
    LIB_PATH, XML_PATH = map(Path, sys.argv[1:])
    LIB = pinned(LIB_PATH, LIB_SHA, 16 * 1024 * 1024)
    XML = pinned(XML_PATH, XML_SHA, 65536)
    unittest.main(argv=[sys.argv[0]])
