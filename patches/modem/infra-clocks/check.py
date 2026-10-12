#!/usr/bin/env python3
"""Check the native CCF table against pinned B4.1 and Linux; no compilation."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
ARCHIVE_SHA512 = "5d809b44f94336549285a559909bfe5d8b2dcc3f213af58c25a52d535cd2cd0345ce34f44e1d155940cf0d4089fd2ad49fa0d6829fd2b965095084cd1500003c"


def committed(root, pin, name):
    return subprocess.check_output(["git", "-C", str(root), "show", pin + ":" + name], text=True)


def gates(source, native=False):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    pattern = (r'GATE_IFRAO\(\s*(\d),\s*' if native else r'GATE_IFRAO(\d)\(\s*')
    pattern += r'(CLK_IFRAO_\w+),\s*"([^"]+)",\s*"([^"]+)",\s*(\d+)\s*\)'
    return [(int(bank), ident, name, parent, int(bit))
            for bank, ident, name, parent, bit in re.findall(pattern, source)]


def registers(source):
    result = {}
    for bank, body in re.findall(r'ifrao(\d)_cg_regs\s*=\s*\{(.*?)\};', source, re.S):
        result[int(bank)] = {key: int(value, 16) for key, value in
                            re.findall(r'\.(\w+_ofs)\s*=\s*(0x[0-9a-fA-F]+)', body)}
    return result


def validate(native, vendor, header, top, vendor_top):
    expected = gates(vendor)
    # The native topckgen drops the vendor's top_ naming prefix. Resolve by
    # clock ID and divider, not similarly named strings or dummy aliases.
    parents = {}
    for symbol in ("CLK_TOP_AXI", "CLK_TOP_F26M", "CLK_TOP_DPMAIF_MAIN"):
        pattern = r'FACTOR\(' + symbol + r',\s*"([^"]+)",\s*"([^"]+)",\s*(\d+),\s*(\d+)\)'
        old, new = re.findall(pattern, vendor_top), re.findall(pattern, top)
        if len(old) != 1 or len(new) != 1 or old[0][2:] != new[0][2:] or \
                old[0][1].removeprefix("top_") != new[0][1]:
            raise ValueError("native topckgen parent identity/divider drift: " + symbol)
        parents[old[0][0]] = new[0][0]
    expected = [(bank, ident, name, parents[parent], bit)
                for bank, ident, name, parent, bit in expected]
    if len(expected) != 13 or gates(native, True) != expected:
        raise ValueError("B4.1 infra gate identity/order drift")
    if registers(native) != registers(vendor) or len(registers(native)) != 5:
        raise ValueError("B4.1 SET/CLR/STA bank drift")
    ids = dict((name, int(value)) for name, value in
               re.findall(r'^#define\s+(CLK_IFRAO_\w+)\s+(\d+)\s*$', header, re.M))
    if [ids.get(row[1]) for row in expected] != list(range(13)) or ids.get("CLK_IFRAO_NR_CLK") != 13:
        raise ValueError("native clock specifier ABI drift")
    for parent in {row[3] for row in expected}:
        if '"' + parent + '"' not in top:
            raise ValueError("missing native clock parent: " + parent)
    for token in ("CLK_IS_CRITICAL", "CLK_IGNORE_UNUSED", "CLK_OPS_PARENT_ENABLE",
                  "ioremap", "readl(", "writel(", "arm_smccc", "pm_runtime_", "reset_control"):
        if token in native:
            raise ValueError("extra hardware policy in CCF table: " + token)
    for token in ("mtk_clk_simple_probe", "mtk_clk_simple_remove", "&mtk_clk_gate_ops_setclr",
                  '"mediatek,mt6878-infracfg-ao"'):
        if token not in native:
            raise ValueError("native provider lifecycle missing: " + token)


def check(vendor, linux_archive):
    upstream = committed(vendor, VENDOR, "drivers/clk/mediatek/clk-mt6878-bus.c")
    vendor_top = committed(vendor, VENDOR, "drivers/clk/mediatek/clk-mt6878.c")
    with linux_archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != ARCHIVE_SHA512:
            raise ValueError("not the pinned Linux archive")
    with tarfile.open(linux_archive) as archive:
        def source(name):
            return archive.extractfile("linux-" + LINUX + "/" + name).read().decode()
        header = source("include/dt-bindings/clock/mediatek,mt6878-clock.h")
        top = source("drivers/clk/mediatek/clk-mt6878-topckgen.c")
    native = (HERE / "clk-mt6878-infra-ao.c").read_text()
    validate(native, upstream, header, top, vendor_top)
    # Mutations must fail even when IDs/counts and provider APIs remain intact.
    for old, new in [('"axi_ck", 12', '"axi_ck", 11'),
                     ('.set_ofs = 0x88', '.set_ofs = 0x84'),
                     ('CLK_IFRAO_CCIF_AP,', 'CLK_IFRAO_CCIF1_AP,'),
                     ('"dpmaif_main_ck"', '"unproven_parent"')]:
        if native.count(old) != 1:
            raise ValueError("mutation anchor drift")
        try:
            validate(native.replace(old, new), upstream, header, top, vendor_top)
        except ValueError:
            pass
        else:
            raise ValueError("invalid gate table accepted")
    print("PASS: 13 native infra gates, five banks, existing parents, four rejected mutations")
    for name, source in [("vendor", upstream), ("linux-header", header), ("native", native)]:
        print(name, hashlib.sha256(source.encode()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", required=True, type=Path)
    parser.add_argument("--linux-archive", required=True, type=Path)
    args = parser.parse_args()
    check(args.vendor, args.linux_archive)
