#!/usr/bin/env python3
"""Read pinned git objects and the kernel archive, without changing checkouts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
KERNEL = "d84b264a54a37611f2f46bc19363cb9b41606205"
VENDOR_REPO = "android_kernel_device_modules_6.1_nothing_mt6878"
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
VENDOR_PATHS = (
    "drivers/soc/mediatek/mtk-scpsys-mt6878.c",
    "drivers/soc/mediatek/mtk-scpsys.c",
    "drivers/soc/mediatek/mtk-scpsys.h",
    "drivers/misc/mediatek/vmm_spm/mtk-vmm-spm.c",
    "drivers/misc/mediatek/vmm/mtk-vmm-notifier.c",
    "drivers/soc/mediatek/mtk-mmdvfs-v3.c",
    "include/linux/soc/mediatek/mtk_sip_svc.h",
    "include/dt-bindings/power/mt6878-power.h",
    "arch/arm64/boot/dts/mediatek/mt6878.dts",
    "arch/arm64/boot/dts/mediatek/mt6878-disable-unused.dtsi",
    "arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts",
)
KERNEL_PATHS = (
    "drivers/pmdomain/mediatek/mtk-pm-domains.c",
    "drivers/pmdomain/mediatek/mtk-pm-domains.h",
    "drivers/regulator/core.c",
)
PATCHES = (
    "0018-pmdomain-mediatek-mt6878-audio.patch",
    "0057-pmdomain-mediatek-add-MT6878-MM_INFRA-and-DISP.patch",
    "0074-pmdomain-mediatek-tolerate-MT6878-HWCCF-EPERM.patch",
)


def one(pattern, text):
    matches = re.findall(pattern, text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError("absent/ambiguous source context: " + pattern)
    return matches[0]


def body_after(text, marker):
    start = text.index("{", text.index(marker))
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    raise ValueError("unclosed source block")


def provenance(repository, commit, path, data):
    return dict(repository=repository, commit=commit, path=path,
                sha256=hashlib.sha256(data).hexdigest())


def trace(upstream):
    rows, sources = [], {}
    for path in VENDOR_PATHS:
        raw = subprocess.check_output(["git", "-C", str(upstream / VENDOR_REPO),
                                       "show", VENDOR + ":" + path])
        rows.append(provenance(VENDOR_REPO, VENDOR, path, raw))
        sources[path] = raw.decode()
    archive = upstream / ("linux-" + KERNEL + ".tar.gz")
    archive_name = "linux-postmarketos-mediatek-mt6878-" + KERNEL + ".tar.gz"
    expected = one(r"^([0-9a-f]{128})  " + re.escape(archive_name) + r"$",
                   (PACKAGE / "APKBUILD").read_text())
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    if actual != expected:
        raise ValueError("kernel archive does not match packaged checksum")
    prefix = "linux-" + KERNEL + "/"
    native = {}
    # Read original archive members, never a potentially patched working tree.
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix(prefix)
            if member.name.startswith(prefix) and path in KERNEL_PATHS:
                native[path] = tar.extractfile(member).read()
    if set(native) != set(KERNEL_PATHS):
        raise ValueError("incomplete pinned kernel archive")
    for path in KERNEL_PATHS:
        rows.append(provenance("MT6878-mainline/linux", KERNEL, path, native[path]))
    for path in PATCHES:
        rows.append(provenance("nothing-tetris-pmaports", "packaged-input", path,
                               (PACKAGE / path).read_bytes()))

    soc = sources[VENDOR_PATHS[0]]
    ids = sources["include/dt-bindings/power/mt6878-power.h"]
    domains = {}
    for name in ("CAM_VCORE", "CAM_MAIN"):
        symbol = "MT6878_POWER_DOMAIN_" + name
        body = body_after(soc, "[" + symbol + "]")
        steps = []
        for set_, clr, enable, sta, mask in re.findall(
                r"BUS_PROT_IGN\(IFR_TYPE,\s*(0x\w+),\s*(0x\w+),\s*(0x\w+),"
                r"\s*(0x\w+),\s*(\w+)\)", body):
            definition = one(r"^#define " + mask + r"\s+([^\n]+)", soc)
            steps.append(dict(set=int(set_, 16), clear=int(clr, 16),
                              enable=int(enable, 16), status=int(sta, 16),
                              bits=[int(b) for b in re.findall(r"BIT\((\d+)\)", definition)],
                              ignore_clear_ack=True))
        domains[name] = dict(id=int(one(r"^#define " + symbol + r"\s+(\d+)", ids)),
                             control=int(one(r"\.ctl_offs = (0x\w+)", body), 16),
                             sram_pdn_bits=[8] if "sram_pdn_bits" in body else [],
                             sram_ack_bits=[12] if "sram_pdn_ack_bits" in body else [],
                             protection=steps)
    edges = re.findall(r"\{MT6878_POWER_DOMAIN_(\w+), MT6878_POWER_DOMAIN_(\w+)\}", soc)
    edges = [list(edge) for edge in edges if edge[1] in domains]
    vmm = sources["drivers/misc/mediatek/vmm_spm/mtk-vmm-spm.c"]
    table = body_after(vmm, "[VMM_SPM_MT6878]")
    isolation = {name: int(one(r"\." + name + r" = (0x\w+|\d+)", table), 0)
                 for name in ("iso_con_status", "iso_con_set", "iso_con_clr",
                              "ext_iso_bit", "iso_din_bit", "latch_en_bit")}
    dts = sources["arch/arm64/boot/dts/mediatek/mt6878.dts"]
    return dict(release="Nothing OS B4.1 Tetris-B4.1-260415-1709", provenance=rows,
                kernel_archive_sha512=actual,
                domains=domains, parent_edges=edges, vmm_isolation=isolation,
                vmm_supply=one(r"cam-vcore-supply = <&(\w+)>;", dts),
                cam_main_subsys_clocks=[list(clock) for clock in re.findall(r"<&(\w+) (CLK_\w+)>;?",
                    one(r"/\* cam_main\*/(.*?)/\*suba\*/", dts))],
                generic_vmm_genpd_notifier_in_soc_dts='"mediatek,vmm_notifier"' in dts,
                mm_infra=body_after(soc, "[MT6878_POWER_DOMAIN_MM_INFRA]"),
                runtime_activation="disabled")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    content = json.dumps(trace(args.upstream), indent=2) + "\n"
    path = HERE / "evidence.json"
    if args.write:
        path.write_text(content)
    elif path.read_text() != content:
        raise SystemExit("pinned source trace differs")
    print("Pinned vendor, kernel archive and packaged supplier trace verified")


if __name__ == "__main__":
    main()
