#!/usr/bin/env python3
"""Cheap source guards only; C compilation/KUnit execution belongs to CI."""
from pathlib import Path

root = Path(__file__).resolve().parent
source = (root / "mt6878-native-video.c").read_text()
tests = (root / "video-lifetime-test.inc").read_text()
for forbidden in ("ioremap(", "writel(", "iommu_attach_device(",
                  "module_platform_driver(", "devm_kzalloc("):
    assert forbidden not in source, forbidden
for required in ("v4l2_async_nf_register", "video_register_device",
                 "media_create_pad_link", "media_pipeline_start",
                 "mt6878_native_capture_probe", "mt6878_native_capture_frame",
                 "mt6878_native_capture_retire", "VB2_MMAP",
                 "queue.max_num_buffers = 1", "cancel_work_sync",
                 "supplier_modules", "suppress_bind_attrs"):
    assert required in source, required
release = source.split("static int video_release(", 1)[1].split(
    "static const struct v4l2_file_operations", 1)[0]
assert release.index("retire(v)") < release.index("vb2_fop_release(file)")
assert "file->private_data = NULL" in release
guard = source.split("static int stream_off(", 1)[1].split(
    "static const struct v4l2_ioctl_ops", 1)[0]
assert guard.index("mutex_unlock(&v->capture.direct.lock)") < guard.index("retire(v)")
assert guard.index("if (ret)") < guard.index("vb2_ioctl_streamoff")
assert "ret = retire_partial(v)" in source
for case in ("native_video_queue_bounds", "native_video_quarantine_no_reentry",
             "native_video_register_reject", "native_video_registration_result",
             "native_video_preflight_reject", "native_video_partial_guard"):
    assert f"KUNIT_CASE({case})" in tests
worker = source.split("static void frame_work(", 1)[1].split(
    "static int retire(", 1)[0]
assert worker.index("preflight(v, raw, pdaf)") < worker.index("mt6878_native_capture_frame")
assert "mt6878_camsv_recipe_inputs(&mapped" in source
assert "vb2_dma_contig_plane_dma_addr" in source
assert "node->vdev.entity.ops = &video_entity_ops" in source
assert "v->registration_error ? v->registration_error" in source
assert "wait_for_completion_timeout(&v->registration_done, timeout)" in source
assert "video_device_release_empty" not in source
assert ".release = video_final_release" in source
unregister = source.split("int mt6878_native_video_unregister(", 1)[1].split(
    "#if IS_ENABLED(CONFIG_KUNIT)", 1)[0]
detach = unregister.index("detach_nodes(v)")
assert unregister.index("mutex_unlock(&v->registration)", detach) < unregister.index("drain_nodes(v,")
for teardown in ("cleanup_nodes(v)", "media_device_unregister", "v4l2_device_unregister", "kfree(v)"):
    assert unregister.index("drain_nodes(v,") < unregister.index(teardown)
for case in ("native_video_pending_open_race", "native_video_last_close_race",
             "native_video_partial_publication"):
    assert f"KUNIT_CASE({case})" in tests
assert "get_device(&open.node->vdev.dev)" in tests
assert "video_release(&file)" in tests
sensor_patch = root.parents[1] / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0112-media-i2c-imx882-v4l2-controls.patch"
added = sensor_patch.read_text().split("@@ -0,0 +1,665 @@\n", 1)[1].split(
    "diff --git", 1)[0]
sensor = "\n".join(line[1:] for line in added.splitlines() if line.startswith("+"))
overlay = (root / "sensor-unbind-policy.patch").read_text()
old = "\n".join(line[1:] for line in overlay.splitlines() if line.startswith(" "))
assert old in sensor, "sensor policy overlay context does not match frozen 0112"
assert overlay.count("+\t\t.suppress_bind_attrs = true,") == 1
print("Native video source guards PASS (not C/KUnit/hardware validation)")
