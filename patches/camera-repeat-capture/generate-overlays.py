#!/usr/bin/env python3
"""Generate review-only overlays against actual published camera sources."""
import argparse
import difflib
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def replace(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def diff(name, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile="a/" + name, tofile="b/" + name))


def overlays():
    native = (HERE.parent / "camera-native-capture/mt6878-native-capture.c").read_text()
    new = replace(native,
        "c->route.route.attempted || n->direct.pair.tx.hw_attempted)",
        "(c->route.route.attempted && !c->route.route.disconnected) ||\n"
        "\t    (n->direct.pair.tx.hw_attempted && !n->direct.pair.tx.quiesced))")
    new = replace(new, "c->route.phy.attempted ||\n",
        "(c->route.phy.attempted && (!c->route.phy.off_attempted ||\n"
        "\t    c->route.phy.configured || c->route.phy.bus.first_error ||\n"
        "\t    !c->route.source_stopped || !c->irq_drained)) ||\n")
    video = (HERE.parent / "camera-native-video/mt6878-native-video.c").read_text()
    with tempfile.TemporaryDirectory(prefix="epoch-video-base-") as name:
        tree = Path(name)
        target = tree / "mt6878-native-video.c"
        target.write_text(video)
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=tree,
                                input=(HERE.parent / "camera-joint-reset/video-cold.patch").read_text(),
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        video = target.read_text()
    updated = replace(video, '#include "mt6878-camera-joint-reset.h"',
                       '#include "mt6878-camera-joint-reset.h"\n#include "mt6878-capture-epoch.h"')
    updated = replace(updated, "\tstruct mt6878_camera_joint_reset joint_reset;",
                       "\tstruct mt6878_capture_epoch *epoch;")
    updated = replace(updated, "\tstruct vb2_v4l2_buffer *raw, *pdaf;\n\tint ret;",
        "\tstruct vb2_v4l2_buffer *raw, *pdaf;\n"
        "\tstruct mt6878_capture_epoch *previous, *next;\n"
        "\tstruct mt6878_camsv_job layout;\n\tint ret;")
    start = updated.index("\tret = mt6878_camera_cold_frame(")
    end = updated.index("\tmutex_lock(&v->capture.direct.lock);", start)
    updated = updated[:start] + '''\tif (!v->epoch) {
\t\tv->epoch = mt6878_capture_epoch_alloc(&v->capture);
\t\tif (IS_ERR(v->epoch)) {
\t\t\tret = PTR_ERR(v->epoch);
\t\t\tv->epoch = NULL;
\t\t\tgoto frame_result;
\t\t}
\t}
\tlayout = v->suppliers.layout;
\tif (v->epoch->warm)
\t\tlayout.sequence = v->epoch->layout.sequence;
\tret = mt6878_capture_epoch_submit(v->epoch, raw, pdaf,
\t\t&layout, &v->suppliers.config, v->suppliers.port, 0);
\tif (!ret)
\t\tret = mt6878_capture_epoch_retire(v->epoch, msecs_to_jiffies(1000));
\tif (!ret) {
\t\tprevious = v->epoch;
\t\tnext = mt6878_capture_epoch_next(previous);
\t\tif (IS_ERR(next)) {
\t\t\tret = PTR_ERR(next);
\t\t} else {
\t\t\tv->epoch = next;
\t\t\tret = mt6878_capture_epoch_free(previous);
\t\t}
\t}
frame_result:
''' + updated[end:]
    updated = replace(updated,
        "\tif (!ret)\n\t\tret = v->capture.platform.stop_error;",
        "\tif (!ret && !v->stopping) {\n"
        "\t\tv->nodes[0].pending = NULL;\n\t\tv->nodes[1].pending = NULL;\n"
        "\t\tv->used = false; /* Fresh epoch exists after real retirement/rearm. */\n\t}")
    updated = replace(updated,
        "\tif (v->stopping || v->used)\n\t\treturn -ESHUTDOWN;\n\treturn vb2_ioctl_qbuf",
        "\tif (v->stopping)\n\t\treturn -ESHUTDOWN;\n"
        "\tif (v->used)\n\t\treturn -EAGAIN; /* Stop/rearm still owns the completed pair. */\n"
        "\treturn vb2_ioctl_qbuf")
    updated = replace(updated,
        "\tret = mt6878_native_capture_retire(&v->capture, msecs_to_jiffies(1500));\n",
        "\tret = mt6878_native_capture_retire(&v->capture, msecs_to_jiffies(1500));\n"
        "\tif (!ret && v->epoch) {\n\t\tret = mt6878_capture_epoch_free(v->epoch);\n"
        "\t\tif (!ret)\n\t\t\tv->epoch = NULL;\n\t}\n")
    return {"epoch-final-retire.patch": diff("mt6878-native-capture.c", native, new),
            "epoch-video.patch": diff("mt6878-native-video.c", video, updated)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, contents in overlays().items():
        path = HERE / name
        if args.check:
            assert path.read_text() == contents, name
        else:
            path.write_text(contents)


if __name__ == "__main__":
    main()
