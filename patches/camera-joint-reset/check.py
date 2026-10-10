#!/usr/bin/env python3
"""Pinned joint-reset sequence and ownership checks, never compile or run C."""
import argparse
from pathlib import Path
import re
import subprocess
import shutil
import tempfile

PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
HERE = Path(__file__).resolve().parent
SENSOR_PATH = Path("drivers/media/i2c/imx882-tetris-stream.c")


def packaged_sensor():
    package = HERE.parents[1] / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
    patch = (package / "0112-media-i2c-imx882-v4l2-controls.patch").read_text()
    section = patch.split(f"+++ b/{SENSOR_PATH}\n", 1)[1].split("diff --git", 1)[0]
    lines = section.splitlines()
    count = int(re.fullmatch(r"@@ -0,0 \+1,(\d+) @@", lines[0])[1])
    assert len(lines[1:]) == count and all(line.startswith("+") for line in lines[1:])
    return "".join(line[1:] + "\n" for line in lines[1:])


def applied_sensor():
    with tempfile.TemporaryDirectory(prefix="camera-sensor-overlay-check-") as name:
        tree = Path(name)
        source = tree / SENSOR_PATH
        source.parent.mkdir(parents=True)
        source.write_text(packaged_sensor())
        overlay = HERE.parent / "camera-seninf-controller/imx882-native-streams.patch"
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=tree,
                                input=overlay.read_text(), text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return source.read_text()


def sensor_off_contract(source):
    # Check executable bodies, not tokens in patch comments or deleted lines.
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    source = " ".join(source.split())
    power = source.split("static int imx882_power(", 1)[1].split("static const", 1)[0]
    assert "if (on) return -EOPNOTSUPP;" in power
    assert "ret = v4l2_subdev_is_streaming(sd) ? -EBUSY : imx882_stop(camera);" in power
    assert power.index("mutex_lock(&camera->lock)") < power.index("imx882_stop(camera)")
    assert power.index("imx882_stop(camera)") < power.index("mutex_unlock(&camera->lock)")
    assert "static const struct v4l2_subdev_core_ops imx882_core_ops = { .s_power = imx882_power, };" in source
    assert "static const struct v4l2_subdev_ops imx882_subdev_ops = { .core = &imx882_core_ops," in source
    stop = source.split("static int imx882_stop(", 1)[1].split("static int", 1)[0]
    assert re.search(r"\{ int ret = 0, cleanup; if \(camera->streaming\) "
                     r"ret = imx882_write\(camera, 0x0100, 0\); "
                     r"cleanup = imx882_power_off\(&camera->power, camera->enabled_supplies, "
                     r"camera->clock_enabled\);", stop)
    off = source.split("static int imx882_power_off(", 1)[1].split("static int", 1)[0]
    assert re.search(r"\{ int ret, err, supply; "
                     r"gpiod_set_value_cansleep\(imx882->reset, 1\); if \(clock_enabled\)", off)
    assert "if (!ret) ret = cleanup;" in stop
    assert "return ret;" in power


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path)
    parser.add_argument("--staged-only", action="store_true",
                        help="Check only actual staged sensor OFF callback; no vendor Git reads")
    parser.add_argument("--kernel-tree", type=Path,
                        help="Also reject an actual staged kernel missing the sensor OFF overlay")
    args = parser.parse_args(argv)
    if args.staged_only:
        if args.kernel_tree is None:
            parser.error("--staged-only requires --kernel-tree")
        source = args.kernel_tree / SENSOR_PATH
        try:
            sensor_off_contract(source.read_text())
        except (OSError, UnicodeError, AssertionError, IndexError) as error:
            parser.exit(1, f"Staged sensor OFF contract FAIL: {source}: {error}\n")
        print("Actual staged sensor OFF contract PASS; no vendor Git/C/KUnit/hardware execution")
        return
    if args.modules_repo is None:
        parser.error("full source check requires --modules-repo")
    prefix = "mtkcam/camsys/isp7sp/cam/"
    show = lambda path: subprocess.check_output(
        ["git", "show", f"{PIN}:{prefix}{path}"], cwd=args.modules_repo, text=True)
    vendor = show("mtk_cam-sv.c").split("void sv_reset_by_camsys_top(", 1)[1]
    vendor = vendor.split("RESET_FAILURE:", 1)[0]
    regs = show("mtk_cam-sv-regs.h")
    assert re.search(r"#define REG_CAM_MAIN_SW_RST_1\s+0x0058", regs)
    assert "cq_dma_sw_ctl & 0x2" in vendor and "100000 /* timeout, us */" in vendor
    assert "3 << ((sv_dev->id) * 2)" in vendor
    phy = show("mtk_csi_phy_3_1/mtk_cam-seninf-hw_phy_3_1.c")
    for operation in ("disable_cammux", "set_cammux_src", "switch_to_cammux_inner_page"):
        assert operation in phy, operation
    assert "tsrec_n_settings_clear" in show("mtk_cam-seninf-tsrec.c")
    pm = (HERE.parent / "camera-native-capture/mt6878-seninf-pm.c").read_text()
    assert "csi = 3 + p->port" in pm and "enable_clock(p, 7)" in pm
    assert "regulator_set_voltage(p->vcore, p->step[5], INT_MAX)" in pm
    drv = show("mtk_cam-seninf-drv.c")
    assert "vcore_voltage, INT_MAX" in drv
    assert "regulator_get_voltage(core->dvfsrc_vcore_power) < vcore_voltage" in drv
    assert "clk_prepare_enable(core->clk[CLK_TOP_CAMTM])" in drv
    cold_power_contract((HERE / "mt6878-camera-cold-reset.c").read_text())
    code = (HERE / "mt6878-camera-joint-reset.c").read_text()
    for forbidden in ("ioremap", "request_mem_region", "synchronize_irq", "enable_irq",
                      "pm_runtime_put_sync_suspend", "regmap_init"):
        assert not re.search(r"\b" + forbidden + r"\w*\s*\(", code), forbidden
    assert "MT6878_SV_STOPPED" in code and "irqd_irq_disabled(data)" in code
    assert "d->pair.tx.hw_attempted && !d->pair.tx.quiesced" in code
    assert "readl_poll_timeout(scq + SV_CQ_RESET, ready, ready & BIT(1), 1, 100000)" in code
    body = code.split("static int joint_run(", 1)[1].split("int mt6878_camera_joint_reset(", 1)[0]
    sequence = ["mt6878_cam_main_prepare(", "joint_preflight(n, layout,",
                "mutex_unlock(&n->direct.lock)",
                "mtk_smi_camera_reset_clamp(n->smi, n->direct.consumer, true)",
                "writel(0, scq + SV_CQ_RESET)", "writel(1, scq + SV_CQ_RESET)",
                "readl_poll_timeout(", "regmap_write(cam_main, CAM_MAIN_SW_RESET, 0)",
                "regmap_write(cam_main, CAM_MAIN_SW_RESET, 3U << (layout->sv_id * 2))",
                "mtk_smi_camera_reset_clamp(n->smi, n->direct.consumer, false)",
                "mt6878_cam_main_retire(&lease)"]
    last = -1
    for item in sequence:
        index = body.index(item)
        assert index > last, item
        last = index
    assert "source_stopped =" not in code and "disconnected =" not in code
    assert "transaction->first_error = ret" in body and "n->first_error = ret" in body
    assert (HERE / "joint-reset-test.inc").read_text().count("KUNIT_CASE(") == 5
    assert body.index("mt6878_cam_main_retire(&lease)") < body.index("mutex_unlock(&n->lock)")
    provider = (HERE.parent / "camera-cam-main-provider/cam-main-lease.inc").read_text()
    pulse = provider.split("int mt6878_cam_main_reset_pulse(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
    assert "return -EOPNOTSUPP" in pulse
    cold = (HERE / "mt6878-camera-cold-reset.c").read_text()
    assert "mt6878_phy_setup(" not in cold and "mt6878_route_setup(" not in cold
    for forbidden in ("source_stopped =", "route.disconnected =", "irq_drained = true;"):
        if forbidden == "irq_drained = true;":
            assert "c->irq_drained = true" not in cold
        else:
            assert forbidden not in cold
    assert cold.index("synchronize_irq(c->tsrec_irq)") < cold.index("mutex_lock(&c->core)")
    assert "core, s_power, 0" in cold and "mt6878_seninf_tsrec_disable(" in cold
    assert "cold_inactive_pages(cold)" in cold and "cold_readback(cold)" in cold
    assert "c->allocated =" not in cold
    sensor_off_contract(applied_sensor())
    if args.kernel_tree:
        sensor_off_contract((args.kernel_tree / SENSOR_PATH).read_text())
    assert cold.index("cold_mapping(&c->pdev->dev)") < cold.index("synchronize_irq(")
    assert body.index("joint_finish(transaction, n, ret, cleanup)") < body.index("mutex_unlock(&n->lock)")
    joint_lock_contract(code)
    with tempfile.TemporaryDirectory(prefix="camera-video-cold-check-") as name:
        tree = Path(name)
        source = HERE.parent / "camera-native-video/mt6878-native-video.c"
        shutil.copyfile(source, tree / source.name)
        result = subprocess.run(["patch", "--dry-run", "--batch", "--fuzz=0", "-p1"],
                                cwd=tree, input=(HERE / "video-cold.patch").read_text(),
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    print("Pinned joint-reset source/order/ownership guards PASS; no C/KUnit/hardware execution")


def cold_power_contract(code):
    power = code.split("static int cold_power(", 1)[1].split("static int cold_mapping(", 1)[0]
    assert "i < c->num_clocks" not in power and "i < 3" in power
    assert "c->clocks[7].clk" in power and "c->route.csi_clock" in power
    assert "c->clocks[3 + port].clk" in power
    assert "voltage <=" not in power and "voltage > c->dvfs[6]" not in power
    assert "return voltage >= c->dvfs[5] ? 0 : -ERANGE;" in power


def joint_lock_contract(code):
    body = code.split("static int joint_run(", 1)[1].split("int mt6878_camera_joint_reset(", 1)[0]
    sequence = ["mt6878_camera_cold_prepare(",
                "receiver_state = v4l2_subdev_lock_and_get_active_state(",
                "mutex_lock(&n->controller.core)", "mutex_lock(&n->direct.lock)",
                "sensor_state = v4l2_subdev_lock_and_get_active_state(",
                "joint_preflight(n, layout,", "mutex_unlock(&n->direct.lock)",
                "readl_poll_timeout("]
    last = -1
    for item in sequence:
        index = body.index(item)
        assert index > last, item
        last = index
    pin = code.split("static int joint_supplier_get(", 1)[1].split("static int joint_preflight(", 1)[0]
    assert pin.index("!READ_ONCE(n->bound)") < pin.index("mutex_lock(&n->lock)")
    assert pin.index("mutex_lock(&n->lock)") < pin.index("get_device(n->platform.cam_main)")
    frame = code.split("int mt6878_camera_cold_frame(", 1)[1]
    order = ["joint_supplier_get(n, &supplier)", "mt6878_cam_main_prepare(supplier, &lease)",
             "mutex_lock(&n->lock)", "joint_bound(n, supplier)",
             "pm_runtime_resume_and_get(n->smi)"]
    last = -1
    for item in order:
        index = frame.index(item)
        assert index > last, item
        last = index
    validate = code.split("static int joint_bound(", 1)[1].split("static int joint_supplier_get(", 1)[0]
    for item in ("lockdep_assert_held(&n->lock)", "!n->bound", "p->retired",
                 "p->direct != &n->direct", "c->capture != p",
                 "p->cam_main != supplier", "c->route.sensor != p->sensor"):
        assert item in validate, item


if __name__ == "__main__":
    main()
