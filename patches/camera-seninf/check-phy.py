#!/usr/bin/env python3
"""Static-only validation. Native fault-injection/object compilation belongs to CI."""
import argparse
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("phy_generator", HERE / "generate-phy.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def check(args):
    data = generator.generate(args.modules_repo, args.device_repo)
    assert (HERE / "mt6878-seninf-phy-data.h").read_text() == data
    assert generator.PATCH.read_text() == generator.patch_text(data)
    smoke = (HERE / "mt6878-seninf-phy-smoke.c").read_text()
    assert '#include "mt6878-seninf-phy.h"' in smoke
    assert "static_assert(ARRAY_SIZE(mt6878_phy_efuse) == 12)" in smoke
    assert "return mt6878_phy_validate(backend, plan, inputs);" in smoke
    assert not re.search(r"\b(?:module_init|module_platform_driver|EXPORT_SYMBOL|mt6878_phy_setup|mt6878_phy_off|readl|writel)\s*\(", smoke)
    makefile = (HERE / "generate.py").read_text()
    assert "mt6878-seninf-phy-smoke" not in makefile
    header = (HERE / "mt6878-seninf-phy.h").read_text()
    assert not re.search(r"\b(?:readl|writel|ioremap|clk_set_rate|regulator_set_voltage|pm_runtime_get_sync)\s*\(", header)
    body = header.split("static inline int mt6878_phy_setup", 1)[1]
    assert body.index("backend->verify(") < body.index("MT6878_PHY_PROGRAM(init")
    order = re.findall(r"MT6878_PHY_PROGRAM\((\w+), ([^)]+)\)", body)
    assert order == [("init", "0"), ("init", "0x1000"), ("efuse", "0"),
                     ("timing", "0"), ("post", "0"), ("mac_top", "0"),
                     ("mac_fixed", "0"), ("mac", "0"), ("lrte_off", "0"),
                     ("seninf", "0"), ("analog_setup", "0"), ("trios", "0")]
    assert body.index("mt6878_seninf_analog_half(") < body.index("MT6878_PHY_PROGRAM(trios")
    assert "&tx->bus.plan, &tx->bus)" in header
    assert "if (tx->bus.first_error)" in body and "if (tx->attempted" in body
    validation = header.split("static inline int mt6878_phy_validate", 1)[1].split("static inline unsigned int", 1)[0]
    assert "in->rg_csi_verified != 1" in validation
    assert "in->rg_csi_port != plan->port" in validation
    assert not re.search(r"!in->rg_csi\b|in->rg_csi\s*(?:==|!=)", validation)
    # Evaluate dynamic generated fields using synthetic data, both halves,
    # every allowed clock, and both exact module modes. No handset data read.
    operations = re.findall(r"\{ (MT6878_SENINF_\w+), (0x[\da-f]+), (0x[\da-f]+)U, (\d+), (MT6878_PHY_\w+), (0x[\da-f]+) \}", data)
    assert len(operations) == 195, len(operations)
    efuses = []
    for region, offset, mask, shift, kind, value in operations:
        offset, mask, shift, value = int(offset, 16), int(mask, 16), int(shift), int(value, 16)
        for port in (0, 1):
            address = offset + (port * 0x8000 if region.endswith("ANALOG") else 11 * 0x1000)
            assert address % 4 == 0
            assert address + 4 <= (0x30000 if region.endswith("ANALOG") else 0x18000)
        if kind == "MT6878_PHY_EFUSE":
            efuses.append((offset, value))
        for clock in (312000000, 343000000, 416000000, 499000000):
            for trail in (0x47, 0x31):
                actual = value
                if kind == "MT6878_PHY_EFUSE":
                    for payload in (0, 0xa5a5a5a4):
                        calibrated = (payload >> value) & 31
                        assert not ((calibrated << shift) & ~mask)
                    actual = (0xa5a5a5a4 >> value) & 31
                elif kind == "MT6878_PHY_SETTLE":
                    actual = (70 * clock + 999999999) // 1000000000 - 6
                elif kind == "MT6878_PHY_TRAIL":
                    ui = 224000 // ((700800000 * 10 // 3) // 1000000)
                    actual = 0 if trail > ui else ((ui - trail) * clock + 999999999) // 1000000000
                assert not ((actual << shift) & ~mask), (offset, kind, actual)
    assert [v for _, v in efuses] == [27, 27, 22, 22, 17, 17, 12, 12, 7, 7, 2, 2]
    assert all(offset < 0x1000 for offset, _ in efuses[:6])
    assert all(offset >= 0x1000 for offset, _ in efuses[6:])
    with tempfile.TemporaryDirectory(prefix="seninf-phy-apply-") as temporary:
        subprocess.run(["patch", "--batch", "-p1", "-i", str(generator.PATCH)], cwd=temporary, check=True)
        installed = Path(temporary) / "drivers/media/platform/mediatek/seninf"
        for name in ("mt6878-seninf-phy.h", "mt6878-seninf-phy-data.h", "mt6878-seninf-phy-smoke.c"):
            assert (installed / name).read_text() == (HERE / name).read_text()
    print("PASS: pinned sensor/clock/register provenance and deterministic patch application")
    print("PASS: exact stage order, calibrated half mapping, all mode/clock field bounds")
    print("Native ASan/UBSan and kernel object tests prepared for main CI; NOT run locally")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    check(parser.parse_args())
