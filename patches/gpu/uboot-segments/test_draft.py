#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Source/integration checks only; native fixtures run exclusively in CI."""
import os
from pathlib import Path
import subprocess
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from check_integration import BASE, BOARD, DEFAULT_TREE, check_sources


class Draft(unittest.TestCase):
    def tree(self):
        return Path(os.environ.get("TETRIS_UBOOT_TREE", str(DEFAULT_TREE)))

    def test_actual_checkout_integration(self):
        check_sources(lambda path: (self.tree() / path).read_text())

    def test_uboot_authentication_does_not_double_transform(self):
        from prepare_native import definition
        board = self.tree() / BOARD
        security = (board / "tetris_scp_security.c").read_text()
        for start in ("int tetris_gpueb_authenticate(", "static int verify_chain(",
                      "static int verify_hw("):
            function = definition(security, start)
            self.assertNotIn("tetris_scp_crypto_decrypt(", function)
            self.assertNotIn("smc(", function)
        self.assertIn("rsa_verify_with_pkey(", definition(security, "static int verify_hw("))
        self.assertIn(".verify = verify_hw", security)
        for name in ("tetris_gpueb_prepare.c", "tetris_gpueb_flat.c"):
            code = (board / name).read_text()
            self.assertEqual(code.count("tetris_gpueb_authenticate("), 1)
            self.assertEqual(code.count("tetris_scp_crypto_decrypt("), 1)
            self.assertLess(code.index("tetris_gpueb_authenticate("),
                            code.index("tetris_scp_crypto_decrypt("))
        crypto = definition((board / "tetris_scp_crypto.c").read_text(),
                            "int tetris_scp_crypto_decrypt(")
        self.assertEqual(crypto.count("ops->smc(TETRIS_SCP_CRYPTO_DECRYPT, selector, 0)"), 1)
        kconfig = (self.tree() / "arch/arm/mach-mediatek/Kconfig").read_text()
        retention = kconfig.split("config TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC", 1)[1]
        self.assertIn("depends on !TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC",
                      retention.split("\nconfig ", 1)[0])

    def test_pinned_fdb0ee29_integration(self):
        def read(path):
            return subprocess.run(["git", "show", f"{BASE}:{path.as_posix()}"],
                                  cwd=self.tree(), check=True, text=True,
                                  capture_output=True).stdout
        check_sources(read)

    def test_partial_or_duplicate_integration_rejected(self):
        sources = {path: (self.tree() / path).read_text() for path in (
            BOARD / "tetris_gpueb_prepare.c", BOARD / "tetris_gpueb_prepare.h",
            BOARD / "Makefile", BOARD / "tetris_gpueb_segments.c",
            BOARD / "tetris_gpueb_segments.h")}
        call = "ret = tetris_gpueb_inspect_segments(staging, size, &result.segments);"
        mutations = (
            ("tetris_gpueb_prepare.c", call, call + "\n\t" + call),
            ("tetris_gpueb_prepare.c", call, "ret = 0;"),
            ("tetris_gpueb_prepare.c", call, call.replace("staging, size", "container, container_size")),
            ("tetris_gpueb_prepare.c", "if (ret)\n\t\tgoto out;\n\tret = tetris_gpueb_describe_plain",
             "ret = 0;\n\tret = tetris_gpueb_describe_plain"),
            ("tetris_gpueb_prepare.c", "out:\n\twipe(staging, capacity);", "out:"),
            ("tetris_gpueb_prepare.c", "return ret;\n}", "return 0;\n}"),
            ("tetris_gpueb_prepare.h", "struct tetris_gpueb_segment_info segments;", ""),
            ("Makefile", "obj-$(CONFIG_TETRIS_SCP_SECURITY) += tetris_gpueb_segments.o",
             "obj-y += tetris_gpueb_segments.o"),
            ("tetris_gpueb_segments.c", "bytes > 0x100000", "bytes > 0x200000"),
        )
        for name, old, new in mutations:
            with self.subTest(name=name, mutation=old):
                path = BOARD / name
                self.assertIn(old, sources[path])
                altered = dict(sources)
                altered[path] = sources[path].replace(old, new, 1)
                with self.assertRaises(ValueError):
                    check_sources(altered.__getitem__)

    def test_obsolete_patch_cannot_duplicate_current_integration(self):
        self.assertFalse((HERE / "prepare-integration.patch").exists())

    def test_no_execution_or_plaintext_export(self):
        code = (HERE / "tetris_gpueb_segments.c").read_text()
        for forbidden in ("printf(", "writel(", "readl(", "smc(", "malloc(", "memcpy("):
            self.assertNotIn(forbidden, code)
        header = (HERE / "tetris_gpueb_segments.h").read_text()
        self.assertNotIn("unsigned char", header)
        self.assertNotIn("upload_allowed", header)

    @unittest.skipUnless(os.environ.get("TETRIS_B41_GPUEB"), "cached firmware not supplied")
    def test_actual_auxiliary_pt_framing_not_executable_map(self):
        from gpueb_firmware import inspect, sections
        from audit_gpueb_lk import ROOT_PIN
        raw = Path(os.environ["TETRIS_B41_GPUEB"]).read_bytes()
        report = inspect(raw, ROOT_PIN)
        self.assertEqual(report["container_sha256"],
                         "58c337b0e713d643a1cb129fd444bce0b8bc00e38877c3f242ac9a7f5901ba22")
        self.assertEqual(report["components"][0]["payload_size"], 156064)
        self.assertEqual(report["components"][1]["whole_payload_digest"], "unproven")
        auxiliary = sections(raw)[3].payload
        self.assertEqual(struct.unpack_from("<6I", auxiliary),
                         (0x58901690, 24, 364416, 4, 99, 0))
        self.assertRegex(auxiliary[24 + 364416:], rb"^END[0-9a-f]{40}$")
        # Framing is visible, not an authentication certificate for its body.
        code = (HERE / "tetris_gpueb_segments.c").read_text()
        pt = code[code.index("static int inspect_pt("):code.index("int tetris_gpueb_inspect_segments(")]
        self.assertNotIn(".memory_bytes =", pt)
        self.assertNotIn(".memory_offset =", pt)

    def test_ci_runner_shell(self):
        result = subprocess.run(["sh", "-n", str(HERE / "run-native-ci.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_gate_targets_verified_upstream_not_review_mirror(self):
        runner = (HERE / "run-native-ci.sh").read_text()
        self.assertLess(runner.index('"$here/check_integration.py"'),
                        runner.index('"${CC:-cc}"'))
        self.assertIn('"$board/tetris_gpueb_segments.c"', runner)
        self.assertIn('-I"$board"', runner)
        self.assertNotIn('"$here/tetris_gpueb_segments.c"', runner)

    def test_ci_runner_rejects_local_values_before_compiler(self):
        for value in (None, "", "0", "false", "1"):
            with self.subTest(CI=value):
                env = dict(os.environ, CC="must-not-invoke-a-compiler")
                env.pop("CI", None)
                if value is not None:
                    env["CI"] = value
                result = subprocess.run(["sh", str(HERE / "run-native-ci.sh")],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("CI-only", result.stderr)

    @unittest.skipUnless(os.environ.get("TETRIS_B41_LK"), "private LK not supplied")
    def test_stock_copy_reads_payload_not_container(self):
        from audit_gpueb_b41 import signed_lk
        from audit_gpueb_lk import expect
        code = signed_lk(Path(os.environ["TETRIS_B41_LK"]).read_bytes())
        for check in (
            (0x1ed8c, "add", "x23, x8, #0x18"),
            (0x1ed90, "mov", "x2, x23"),
            (0x1ed94, "bl", "#0x74da0"),
            (0x74dc8, "mov", "x21, x2"),
            (0x75180, "ldr", "w25, [x19, #4]"),
            (0x7518c, "add", "x24, x27, #0x200"),
            (0x75024, "mov", "x1, x21"),
            (0x75028, "mov", "x2, x24"),
            (0x7502c, "mov", "x3, x25"),
            (0x75030, "bl", "#0x67edc"),
            (0x75060, "ldr", "w8, [x19]"),
            (0x75064, "mov", "w9, #0xab1e"),
            (0x75068, "movk", "w9, #0xd7b7, lsl #16"),
            (0x75070, "cmp", "w8, w9"),
            (0x75074, "csel", "w8, w28, wzr, eq"),
            (0x75078, "add", "x21, x21, x8"),
            (0x7507c, "sub", "x25, x25, x8"),
            (0x75080, "mov", "x0, x21"),
            (0x75084, "mov", "w1, w25"),
            (0x75088, "bl", "#0x7e344"),
            (0x750bc, "mov", "x0, x21"),
            (0x750c0, "mov", "w1, w25"),
            (0x750c4, "bl", "#0x7e348"),
            (0x1ede8, "mov", "w2, #0x40000"),
            (0x1ee00, "mov", "w8, #0xf2bc"),
            (0x1ee04, "movk", "w8, #3, lsl #16"),
            (0x1ee08, "ldr", "w9, [x23], #4"),
            (0x1ee0c, "sub", "w8, w8, #4"),
            (0x1ee10, "cmp", "w8, #4"),
            (0x1ee14, "str", "w9, [x26], #4"),
            (0x1ee18, "b.hi", "#0x1ee08"),
            # Matching PT framing is also present in B4.1's APUSYS reader.
            # Its dispatch roles MUST NOT be assigned to GPUEB ID values.
            (0x17848, "mov", "w13, #0x1690"),
            (0x1784c, "movk", "w13, #0x5890, lsl #16"),
            (0x178c4, "ldp", "w8, w9, [x21, #8]"),
            (0x178c8, "add", "w8, w8, w9"),
            (0x178cc, "neg", "w9, w9"),
            (0x178d0, "sub", "w8, w8, #1"),
            (0x178d4, "and", "x8, x8, x9"),
            (0x178e8, "ldr", "w8, [x21, #4]"),
            (0x178ec, "ldr", "w1, [x21, #0x10]"),
            (0x178f0, "add", "x23, x21, x8"),
        ):
            expect(code, *check)
        # Only the legacy 0xd7b7ab1e header advances the destination before
        # transform. Our primary's 0x58881688 header stays in temporary x19.
        self.assertNotEqual(0x58881688, 0xd7b7ab1e)
        # This is a loop extent, not an authenticated expansion-size ABI.
        self.assertEqual(0x3f2bc - 4, 258744)
        self.assertEqual(258744 - 156064, 102680)


if __name__ == "__main__":
    unittest.main()
