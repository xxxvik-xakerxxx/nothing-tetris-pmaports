#!/usr/bin/env python3
"""Source/overlay guards only; never compile or operate camera hardware."""
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
source = (HERE / "cam-main-lease.inc").read_text()
patch = (HERE / "provider.patch").read_text()
subprocess.run(["git", "apply", "--numstat", str(HERE / "provider.patch")],
               cwd=ROOT, check=True, capture_output=True)
packaged = (ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/"
            "0092-clk-mediatek-mt6878-camera-main.patch").read_text()
section = packaged.split("+++ b/drivers/clk/mediatek/clk-mt6878-cam.c\n", 1)[1]
lines = [line[1:] for line in section.splitlines()
         if line.startswith("+") and not line.startswith("+++")]
hunk = patch.split("@@", 2)[2].splitlines()[1:]
old = [line[1:] for line in hunk if line.startswith((" ", "-"))]
assert any(lines[i:i + len(old)] == old for i in range(len(lines))), "overlay drift"
for forbidden in ("ioremap", "request_mem_region", "regmap_init", "devm_",
                  "writel", "regmap_write"):
    assert not re.search(r"\b" + forbidden + r"\w*\s*\(", source), forbidden
prepare = source.split("int mt6878_cam_main_prepare(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
assert prepare.index("device_trylock") < prepare.index("pm_runtime_get_sync")
assert prepare.index("pm_runtime_get_sync") < prepare.index("lease->regmap = map")
assert "pm_runtime_put_noidle(supplier)" in prepare
assert 'of_device_is_compatible(supplier->of_node, "syscon")' in prepare
assert "syscon_node_to_regmap(supplier->of_node)" in prepare
retire = source.split("int mt6878_cam_main_retire(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
assert retire.index("lease->task != current") < retire.index("device_unlock")
assert retire.index("*slot = NULL") < retire.index("pm_runtime_put_sync")
assert retire.index("pm_runtime_put_sync") < retire.index("device_unlock")
reset = source.split("int mt6878_cam_main_reset_pulse(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
assert "return -EOPNOTSUPP" in reset
assert ".suppress_bind_attrs = true" in patch
tests = (HERE / "cam-main-lease-test.inc").read_text()
assert tests.count("KUNIT_CASE(") == 4
print("CAM_MAIN source/overlay guards PASS (no C/KUnit execution)")
