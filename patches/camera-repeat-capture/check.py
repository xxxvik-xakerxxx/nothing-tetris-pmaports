#!/usr/bin/env python3
"""Source/overlay checks only; never execute a camera or C compiler."""
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def completion_contract(code):
    retire = code.split("int mt6878_capture_epoch_retire(", 1)[1].split(
        "struct mt6878_capture_epoch *mt6878_capture_epoch_next(", 1)[0]
    wait = retire.index("if (!wait_for_completion_timeout(")
    stop = retire.index("mt6878_camsv_platform_stop_async(")
    flush = retire.index("flush_work(")
    assert "mt6878_camsv_platform_stop_async(" not in retire[:wait]
    timeout = retire[wait:flush]
    assert wait < stop < flush
    for item in ("ret = -ETIMEDOUT;", "epoch_error(e, ret);",
                 "n->first_error = e->first_error;", "d->first_error = e->first_error;",
                 "mutex_unlock(&d->lock)", "mutex_unlock(&n->lock)"):
        assert timeout.index(item) < timeout.index("mt6878_camsv_platform_stop_async("), item
    assert "goto fail;" in timeout[timeout.index("mt6878_camsv_platform_stop_async("):]
    assert timeout.count("mt6878_camsv_platform_stop_async(") == 1


def main():
    code = (HERE / "mt6878-capture-epoch.c").read_text()
    completion_contract(code)
    platform = (HERE.parent / "camera-direct-platform/mt6878-camsv-platform.c").read_text()
    irq = platform.split("static irqreturn_t platform_irq(", 1)[1].split(
        "static void platform_stop_work(", 1)[0]
    assert "stop = ret == 1 ||" in irq
    assert irq.index("mt6878_camsv_direct_done(d)") < irq.index("mt6878_camsv_platform_stop_async(p)")
    retire = code.split("int mt6878_capture_epoch_retire(", 1)[1]
    ordered = ["wait_for_completion_timeout(", "flush_work(",
               "e->dma_receipt = d->pair.tx", "mt6878_camera_joint_reset(",
               "synchronize_irq(", "mt6878_seninf_route_retire(",
               "dma_free_coherent(", "e->retired = true"]
    last = -1
    for item in ordered:
        index = retire.index(item)
        assert index > last, item
        last = index
    for forbidden in ("memset(", "attempted = false", "first_error = 0", "quiesced =",
                      "ioremap", "enable_irq(", "mutex_init(&n->", "free_irq(",
                      "pm_runtime_put", "mt6878_native_capture_retire("):
        assert forbidden not in code, forbidden
    assert "n->epoch = e" in code and "n->epoch != e" in code
    assert "n->direct.encoder.finished" in code
    assert "d->pair.tx.complete_tags == tags" in code and "!d->pair.raw && !d->pair.pdaf" in code
    assert (HERE / "epoch-test.inc").read_text().count("KUNIT_CASE(") == 5
    next_frame = code.split("struct mt6878_capture_epoch *mt6878_capture_epoch_next(", 1)[1]
    assert next_frame.index("!old->retired") < next_frame.index("dma_alloc_coherent(")
    assert next_frame.index("dma_alloc_coherent(") < next_frame.index("c->route = fresh")
    assert "next->layout.sequence++" in next_frame
    assert "!d->pair.tx.submitted" in code
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("epoch_overlays", HERE / "generate-overlays.py")
    generator = module_from_spec(spec)
    spec.loader.exec_module(generator)
    for name, contents in generator.overlays().items():
        assert (HERE / name).read_text() == contents, name
    with tempfile.TemporaryDirectory(prefix="capture-epoch-check-") as name:
        tree = Path(name)
        header = HERE.parent / "camera-native-capture/mt6878-native-capture.h"
        shutil.copyfile(header, tree / header.name)
        result = subprocess.run(["patch", "--dry-run", "--batch", "--fuzz=0", "-p1"],
                                cwd=tree, input=(HERE / "epoch-owner.patch").read_text(),
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        source = HERE.parent / "camera-direct-platform/mt6878-camsv-platform.c"
        target = tree / source.name
        shutil.copyfile(source, target)
        for overlay in ("camera-seninf-controller/native-bind.patch",
                        "camera-native-capture/native-pm.patch"):
            text = (HERE.parent / overlay).read_text()
            section = "--- a/mt6878-camsv-platform.c\n" + text.split(
                "--- a/mt6878-camsv-platform.c\n", 1)[1].split("--- a/", 1)[0]
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=tree, input=section, text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                cwd=tree, input=(HERE / "epoch-stop-lock.patch").read_text(),
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        stop = target.read_text().split("static void platform_stop_work(", 1)[1].split(
            "int mt6878_camsv_platform_bind(", 1)[0]
        call = stop.index("mt6878_camsv_direct_stop(d)")
        lock = stop.index("mutex_lock(&p->native_capture->reset_lock)")
        unlock = stop.index("mutex_unlock(&p->native_capture->reset_lock)")
        assert lock < call < unlock
        assert stop.index("mt6878_native_capture_receiver_stop(p)") < lock
        assert stop.index("mutex_lock(&d->lock)", stop.index("mt6878_native_capture_receiver_stop(p)")) < lock
        assert unlock < stop.index("mutex_unlock(&d->lock)", call)
        native = HERE.parent / "camera-native-capture/mt6878-native-capture.c"
        shutil.copyfile(native, tree / native.name)
        video = HERE.parent / "camera-native-video/mt6878-native-video.c"
        shutil.copyfile(video, tree / video.name)
        for path in (HERE.parent / "camera-joint-reset/video-cold.patch",
                     HERE / "epoch-final-retire.patch", HERE / "epoch-video.patch"):
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=tree, input=path.read_text(), text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
        worker = (tree / video.name).read_text()
        assert "mt6878_capture_epoch_submit(v->epoch" in worker
        assert worker.index("mt6878_capture_epoch_next(previous)") < worker.index("v->used = false;")
        assert worker.index("cancel_work_sync(&v->frame_work)") < worker.index("mt6878_capture_epoch_free(v->epoch)")
    print("Persistent frame-retire/rearm/overlay source guards PASS; ARM/KUnit/runtime pending")


if __name__ == "__main__":
    main()
