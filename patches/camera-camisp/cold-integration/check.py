#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic source/patch/ownership checks, never a hardware or compile test."""
import argparse
import json
import re

import generate as gen

EXPORT_OWNER = {
    'mt6878_camera_vmm_check': gen.PD + 'mt6878-native-vmm.inc',
    'mt6878_camera_vmm_validate_domain': gen.PD + 'mt6878-native-vmm.inc',
    'mtk_smi_camera_reset_clamp': 'drivers/memory/mt6878-smi-camera-reset.inc',
    'mt6878_camisp_dma_idle': 'drivers/memory/mt6878-camisp-smi.inc',
    'mt6878_cam_main_prepare': 'drivers/clk/mediatek/cam-main-lease.inc',
    'mt6878_cam_main_regmap': 'drivers/clk/mediatek/cam-main-lease.inc',
    'mt6878_cam_main_retire': 'drivers/clk/mediatek/cam-main-lease.inc',
    'mt6878_cold_capture_register': gen.DIR + 'cold-capture.c',
    'mt6878_native_video_wait_ready': gen.DIR + 'mt6878-native-video.c',
    'mt6878_native_video_unregister': gen.DIR + 'mt6878-native-video.c',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contracts(base, output, evidence):
    files = {**base, **output}
    require(not any(p.startswith("arch/") for p in output), "DT activation is outside this closure")
    kconfig = files[gen.DIR + "Kconfig"]
    require('\tbool ' in kconfig and '\tdefault n\n' in kconfig,
            "capture must be built-in only and default off")
    for dependency in ("MTK_SMI=y", "MTK_IOMMU=y", "MTK_SCPSYS_PM_DOMAINS=y", "COMMON_CLK_MT6878_CAM=y"):
        require(dependency in kconfig, "provider not constrained built-in: " + dependency)
    make = files[gen.DIR + "Makefile"]
    units = re.findall(r"\b[\w-]+\.o\b", make)
    require(units[0] == "mt6878-cold-capture.o", "missing real composite owner")
    require(units[1:] == evidence["production_units"] and len(units) == len(set(units)), "Kbuild unit drift")
    for unit in units[1:]:
        require(gen.DIR + unit.removesuffix(".o") + ".c" in files, "unresolved production unit: " + unit)
        require(not re.search(r"smoke|kunit|test|ccd-bus|worker", unit), "test/CCD bus substituted for owner")
    for path, text in files.items():
        if not path.startswith(gen.DIR):
            continue
        for header in re.findall(r'^#include "([^"/]+)"', text, re.M):
            require(gen.DIR + header in files, "unresolved production include: " + header)
    require('ifneq ($(CONFIG_VIDEO_MT6878_COLD_CAPTURE),y)' in files[gen.SENINF_MAKEFILE],
            "duplicate graph owner would be linked")
    require('obj-$(CONFIG_VIDEO_MT6878_COLD_CAPTURE) += tetris-cold/' in files[gen.MEDIA_MAKEFILE],
            "composite not connected to real media Kbuild")
    require('clk-mt6878-camisp-resources.o' in files["drivers/clk/mediatek/Makefile"], "missing gate provider Kbuild")
    for symbol, path in EXPORT_OWNER.items():
        require('EXPORT_SYMBOL_GPL(' + symbol + ')' in files[path], 'missing real provider export: ' + symbol)

    sensor = files[gen.stream.DRIVER]
    frozen = gen.stream.payload(base)[gen.stream.DRIVER]
    for name in ("static int imx882_mclk_acquire", "static void imx882_mclk_release",
                 "static int imx882_stop", "static int imx882_power_on", "static int imx882_power_off"):
        require(gen.function(sensor, name) == gen.function(frozen, name), "frozen lifecycle drift: " + name)
    require('.s_stream = v4l2_subdev_s_stream_helper,' in sensor and
            '.enable_streams = imx882_enable_streams,' in sensor and
            '.disable_streams = imx882_disable_streams,' in sensor, "missing actual sensor pad stream lifecycle")
    locked = gen.function(sensor, "static int imx882_stream_locked")
    require('lockdep_assert_held(&camera->lock)' in locked and 'mutex_lock' not in locked,
            "sensor active-state callback would recursively lock")
    power = gen.function(sensor, "static int imx882_power(")
    require('v4l2_subdev_is_streaming(sd) ? -EBUSY : imx882_stop(camera)' in power,
            "cold cleanup must reject an active stream and use checked stop")
    route = files[gen.DIR + "mt6878-seninf-route.c"]
    require('v4l2_subdev_call_state_active(r->sensor, pad, get_fmt, &fmt)' in route and
            'get_fmt, NULL' not in route, "NULL active sensor state")
    media = base["drivers/media/v4l2-core/v4l2-subdev.c"]
    require('v4l2_subdev_lock_and_get_active_state(sd)' in gen.function(media, "int v4l2_subdev_enable_streams("),
            "pinned pad stream lock contract drift")

    vmm = files[gen.PD + "mt6878-native-vmm.inc"]
    accessor = gen.function(vmm, "int mt6878_camera_vmm_check(")
    attachment = gen.function(vmm, "static struct scpsys_domain *scpsys_camera_domain(")
    require(attachment.index('ops.runtime_resume != scpsys_vmm_resume') < attachment.index('pd_to_genpd('),
            "unsafe genpd container conversion before actual owner identification")
    for anchor in ('genpd->power_on != scpsys_vmm_on', 'pd->vmm_id != domain'):
        require(anchor in attachment, "actual domain attachment gate missing: " + anchor)
    for anchor in ('scpsys_camera_domain(consumer, domain)', '!pm_runtime_active(consumer)',
                   'mt6878_vmm_check(&pd->scpsys->vmm->supplier)'):
        require(anchor in accessor, "actual supplier gate missing: " + anchor)
    disabled = files[gen.HEADER].split('#else', 1)[1]
    require(disabled.count('return -EOPNOTSUPP;') == 2 and 'return 0;' not in disabled,
            "disabled supplier stub claims success")
    for legacy in ('mediatek,vmm_notifier', 'mediatek,mtk-mmdvfs-v3'):
        require(legacy in vmm, "firmware voter admission veto removed")
    require('pd->genpd.domain.ops.runtime_resume = scpsys_vmm_resume' in files[gen.PD + "mtk-pm-domains.c"],
            "cached-ON consumer resumes bypass actual VMM owner")
    hw = files[gen.DIR + "mt6878-camsv-hardware.c"]
    require('mt6878_camera_vmm_check(p->cam_main, MT6878_POWER_DOMAIN_CAM_MAIN)' in gen.function(hw, 'static int resources('),
            "CAMSV powered access not tied to supplier")
    pm = files[gen.DIR + "mt6878-seninf-pm.c"]
    resume = gen.function(pm, 'int mt6878_seninf_pm_resume(')
    require(resume.index('mt6878_camera_vmm_validate_domain(') < resume.index('pm_runtime_resume_and_get('),
            "receiver requests resume before domain owner validation")
    platform = gen.function(files[gen.DIR + 'mt6878-camsv-platform.c'], 'int mt6878_camsv_platform_power_get(')
    require(platform.index('mt6878_camera_vmm_validate_domain(') < platform.index('pm_runtime_resume_and_get('),
            "CAMSV requests resume before domain owner validation")
    require('mt6878_camera_vmm_check(p->domains[0], MT6878_POWER_DOMAIN_CAM_MAIN)' in pm,
            "receiver resume not tied to actual domain supplier")
    require('p->first_error ? p->first_error : release(p)' in pm,
            "failed supplier path unwinds retained receiver leases")

    capture = files[gen.DIR + "cold-capture.c"]
    for anchor in ('device_is_bound', 's->dma == &s->pdev->dev', 'id ? 13 : 14', 'common != 31',
                   'receiver == s->receiver', 'DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER'):
        require(anchor in capture, "actual supplier topology guard missing: " + anchor)
    require(capture.count('device_link_add(') == 3 and
            capture.count('DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER') == 3,
            "missing actual runtime-PM supplier links")
    require('return mt6878_native_video_register(suppliers, result);' in capture,
            "entry disconnected from actual capture/video owner")
    video = files[gen.DIR + "mt6878-native-video.c"]
    require('mt6878_cold_suppliers_check(s)' in gen.function(video, 'int mt6878_native_video_register('),
            "supplier checks not installed at real constructor")
    require('mt6878_camera_cold_probe(' in video and 'mt6878_camera_cold_frame(' in video,
            "video owner bypasses joint cold reset/capture path")
    for symbol in ('mt6878_native_video_wait_ready', 'mt6878_native_video_unregister'):
        require('EXPORT_SYMBOL_GPL(' + symbol + ')' in video, "missing capture lifetime export: " + symbol)
    for path in evidence["adopted_tracked_sha256"]:
        require(not path.startswith('patches/camera-ccd-bus/'), "unresolved CCD source adopted")

    rail = files[gen.rail.DRIVER]
    require(rail == (gen.HERE.parent / 'rail-owner/tetris-camera-gpio-regulator.c').read_text(),
            "frozen rail provider altered")


def check(archive, device_repo, modules_repo):
    base, output, patch, evidence = gen.build(archive, device_repo, modules_repo)
    require((gen.HERE / 'cold-integration.patch').read_text() == patch, "stale integrated patch")
    require(json.loads((gen.HERE / 'evidence.json').read_text()) == evidence, "stale source evidence")
    contracts(base, output, evidence)
    return base, output, evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    gen.stream.arguments(parser)
    args = parser.parse_args()
    check(args.kernel_archive, args.device_repo, args.modules_repo)
    print('PASS: exact pinned production closure, supplier call sites and strict patch application; no compilation')
