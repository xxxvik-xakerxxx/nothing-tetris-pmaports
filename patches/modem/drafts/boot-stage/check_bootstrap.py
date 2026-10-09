#!/usr/bin/env python3
"""Static draft checks locally; actual caller/transport C faults only in CI."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "bffec9306e7c40a432d79deefb450230c2ee2360"
BOARD = "board/mediatek/mt6878/"
SOURCES = (
    "tetris_modem_layout.c", "tetris_modem_layout.h",
    "tetris_modem_emi.c", "tetris_modem_emi.h",
    "tetris_modem_remap.c", "tetris_modem_remap.h",
    "tetris_scp_security.h",
)


def static_check():
    source = (HERE / "tetris_modem_bootstrap.c").read_text()
    secure = (HERE / "tetris_modem_boot_secure.c").read_text()
    ordered = [
        "ret = md_boot_plan();", "tetris_modem_boot_secure_open(dev, &secure)",
        "ret = md_boot_cold_off();", "tetris_modem_boot_secure_range(secure",
        "tetris_modem_boot_secure_remap(secure", "md_boot_ccci(8, 0)",
        "writel(value & ~MD_CLOCK", "writel(value & ~3U",
        "writel(value | MD_ON", "writel(0xc0, (volatile void *)MD_NEMI_CLR)",
        "writel(0x800, (volatile void *)MD_IFR11_CLR)",
        "writel(0x200, (volatile void *)MD_IFR9_CLR)",
        "md_boot_ccci(6, 1)", "md_boot_ccci(6, 7)",
    ]
    positions = [source.index(item) for item in ordered]
    assert positions == sorted(positions), "bootstrap operation order changed"
    assert "boot.report.reply[2] == 0x100000001ULL" in source
    assert "boot.report.reply[3] == 0x100000001ULL" in source
    assert "#define MD_ACK (3U << 30)" in source
    assert "#define MD_BROM_COUNT 100" in source
    assert "if (boot.attempted)" in source
    cleanup = source[source.index("static void md_boot_cleanup(void)\n{"):
                     source.index("static unsigned int md_boot_read")]
    off_order = ["MD_IFR9_SET", "MD_IFR11_SET", "MD_NEMI_SET",
                 "writel(value & ~MD_ON", "md_cleanup_wait(MD_POWER",
                 "writel(value | 3U", "writel(value | MD_CLOCK"]
    positions = [cleanup.index(item) for item in off_order]
    assert positions == sorted(positions), "LK shutdown/isolation ordering changed"
    assert "boot.mutated && !boot.cleanup_attempted" in source
    assert "boot.report.cleanup.error = -ETIMEDOUT" in source
    assert "session->report.error = error < 0 ? error : -EPROTO" in secure
    for forbidden in ("MD_RESET", "PWR_ON_2ND", "fdt_setprop", "while (1)",
                      "md_boot_ccci(6, 5)", "md_boot_ccci(6, 0)"):
        assert forbidden not in source, forbidden
    print("PASS: static ON/OFF order/bounds/four-one/no-reset/one-attempt checks; NOT C compilation")


def native_ci(uboot):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-md-bootstrap-") as directory:
        root = Path(directory)
        for name in SOURCES:
            data = subprocess.check_output(
                ["git", "-C", str(uboot), "show", f"{PIN}:{BOARD}{name}"])
            (root / name).write_bytes(data)
        for name in ("tetris_modem_boot_secure.c", "tetris_modem_boot_secure.h",
                     "tetris_modem_bootstrap.c", "tetris_modem_bootstrap.h",
                     "test_bootstrap.c"):
            (root / name).write_bytes((HERE / name).read_bytes())
        headers = {
            "asm/io.h": "unsigned int readl(const volatile void *);\n"
                        "void writel(unsigned int, volatile void *);\n",
            "asm/system.h": "unsigned int current_el(void);\n",
            "linux/errno.h": "#include <asm-generic/errno.h>\n",
            "linux/string.h": "#include <string.h>\n",
            "linux/delay.h": "void udelay(unsigned long);\n"
                             "#define mdelay(ms) udelay((ms) * 1000UL)\n",
            "linux/arm-smccc.h": (
                "#ifndef TEST_SMCCC_H\n#define TEST_SMCCC_H\n"
                "struct arm_smccc_res { unsigned long a0, a1, a2, a3; };\n"
                "void test_smc(unsigned long, unsigned long, unsigned long, "
                "unsigned long, unsigned long, unsigned long, unsigned long, "
                "unsigned long, struct arm_smccc_res *);\n"
                "#define arm_smccc_smc test_smc\n#endif\n"),
        }
        for name, data in headers.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        binary = root / "faults"
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1",
            "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(root),
            *(str(root / name) for name in (
                "tetris_modem_layout.c", "tetris_modem_emi.c", "tetris_modem_remap.c",
                "tetris_modem_boot_secure.c", "tetris_modem_bootstrap.c",
                "test_bootstrap.c")), "-o", str(binary),
        ], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        for case in range(37):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        print("PASS: 37 sanitizer cases, actual C caller/secure transport/EMI/remap planners/cleanup")
        print("Mocked hardware/profile I/O only; no AUTH, handset or functional SIM claim")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--uboot", type=Path)
    args = parser.parse_args()
    static_check()
    if args.native_ci:
        if not args.uboot:
            parser.error("--native-ci requires --uboot")
        native_ci(args.uboot)


if __name__ == "__main__":
    main()
