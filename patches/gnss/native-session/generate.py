#!/usr/bin/env python3
"""Opt-in read-only 1010, generated against the exact existing 1001..1009 stack."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("gnss_session_stack", HERE.parent / "write-boundary/generate.py")
write = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = write
spec.loader.exec_module(write)
PIN, MODULES, BASE = write.PIN, write.MODULES, write.BASE
DEVICE = write.DEVICE
FSM = BASE + "hal/gps_dsp_fsm.c"
FSM_H = BASE + "hal/inc/gps_dsp_fsm.h"
UAPI = BASE + "linux/inc/uapi/gpsdl_v051_session.h"
PATCH = HERE / "1010-vendor-gnss-readonly-session-snapshot.patch.vendor"
SNAPSHOT = """static int gps_each_device_session_snapshot(struct gps_each_device *dev, unsigned long arg)
{
	struct gpsdl_v051_session_snapshot result = {
		.abi_version = GPSDL_V051_SESSION_ABI,
		.size = sizeof(result),
	};
	struct gps_each_link *link;
	enum gps_dl_link_id_enum id;
	enum gps_dsp_state_t before;

	if (!dev || dev->index < 0 || (unsigned int)dev->index >= GPS_DATA_LINK_NUM)
		return -ENODEV;
	if (!arg)
		return -EINVAL;
	if (!READ_ONCE(dev->is_open))
		return -ENOTCONN;
	id = (enum gps_dl_link_id_enum)dev->index;
	link = gps_dl_link_get(id);
	if (!link)
		return -ENODEV;
	before = gps_dsp_state_snapshot(id);
	gps_each_link_spin_lock_take(id, GPS_DL_SPINLOCK_FOR_LINK_STATE);
	result.link_id = id;
	result.session_id = READ_ONCE(link->session_id);
	result.link_state = READ_ONCE(link->state_for_user);
	gps_each_link_spin_lock_give(id, GPS_DL_SPINLOCK_FOR_LINK_STATE);
	result.dsp_state = gps_dsp_state_snapshot(id);
	if (!READ_ONCE(dev->is_open))
		return -ENOTCONN;
	if (before != result.dsp_state)
		return -EAGAIN;
	/* No lock covers the DSP and link together. Return samples, not a claim
	 * of atomicity, readiness authorization or a successful firmware action.
	 */
	if (copy_to_user((void __user *)arg, &result, sizeof(result)))
		return -EFAULT;
	return 0;
}

"""
DSP_READER = """enum gps_dsp_state_t gps_dsp_state_snapshot(enum gps_dl_link_id_enum link_id)
{
	ASSERT_LINK_ID(link_id, GPS_DSP_ST_MAX);
	return READ_ONCE(g_gps_dsp_state[link_id]);
}

"""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("source anchor missing or ambiguous: " + old)
    return text.replace(old, new, 1)


def baseline(modules=MODULES):
    manifest = json.loads((write.HERE / "STAGING.json").read_text())
    if hashlib.sha512(write.PATCH.read_bytes()).hexdigest() != manifest["patch_sha512"]:
        raise ValueError("exact1009 identity changed")
    with tempfile.TemporaryDirectory(prefix="session-stack-", dir=HERE) as directory:
        write.populate(directory, modules)
        write.checked(["git", "apply", "--whitespace=error", str(write.PATCH)], directory)
        return {DEVICE: (Path(directory) / DEVICE).read_text(),
                FSM: (Path(directory) / FSM).read_text(),
                FSM_H: write.source(FSM_H, modules), UAPI: ""}


def transform(path, text):
    if path == DEVICE:
        text = once(text, "#include <asm/arch_timer.h>\n", "#include <asm/arch_timer.h>\n#include <linux/compiler.h>\n#include \"uapi/gpsdl_v051_session.h\"\n")
        text = once(text, "static_assert(sizeof(struct gpsdl_v051_bootup_info) == 20);\n",
                    "static_assert(sizeof(struct gpsdl_v051_bootup_info) == 20);\nstatic_assert(sizeof(struct gpsdl_v051_session_snapshot) == 32);\n")
        text = once(text, "static int gps_each_device_ioctl_inner(", SNAPSHOT + "static int gps_each_device_ioctl_inner(")
        return once(text, "\tswitch (cmd) {\n", "\tswitch (cmd) {\n\tcase GPSDL_V051_IOC_SESSION_SNAPSHOT:\n\t\treturn gps_each_device_session_snapshot(dev, arg);\n")
    if path == FSM:
        text = once(text, '#include "gps_dsp_fsm.h"\n', '#include "gps_dsp_fsm.h"\n#include <linux/compiler.h>\n')
        return once(text, "enum gps_dsp_state_t gps_dsp_state_get(", DSP_READER + "enum gps_dsp_state_t gps_dsp_state_get(")
    if path == FSM_H:
        anchor = "enum gps_dsp_state_t gps_dsp_state_get(enum gps_dl_link_id_enum link_id);\n"
        return once(text, anchor, anchor + "enum gps_dsp_state_t gps_dsp_state_snapshot(enum gps_dl_link_id_enum link_id);\n")
    if path == UAPI and text == "":
        return (HERE / "gpsdl_v051_session.h").read_text()
    raise ValueError("out-of-scope or already staged source")


def generate(original):
    chunks = ["Subject: [PATCH] gps: expose read-only live session/FSM samples\n\n"
              "Base: NothingOSS/android_kernel_modules_nothing_mt6878\n"
              "Commit: " + PIN + "\nPrerequisite: exact package 1001..1009, in order\n\n"
              "Future opt-in 1010 only. No default package activation, hardware/FW writes,\n"
              "assert/reset, wakeup, sleep, poll or readiness token. Existing ioctl12/13\n"
              "remain untouched. ioctl31 reads only the real open device's link/session\n"
              "and READ_ONCE DSP state. It is a sampled ABI, not an atomic transition.\n\n"]
    for path, old in original.items():
        new = transform(path, old)
        chunks.append("diff --git a/" + path + " b/" + path + "\n")
        if not old:
            chunks.append("new file mode 100644\n")
        chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                      fromfile="a/" + path if old else "/dev/null", tofile="b/" + path))
    return "".join(chunks)


def fixture(original):
    device = transform(DEVICE, original[DEVICE])
    fsm = transform(FSM, original[FSM])
    return (write.function_span(fsm, "gps_dsp_state_snapshot").text(fsm) + "\n" +
            write.function_span(device, "gps_each_device_session_snapshot").text(device) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=MODULES)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = generate(baseline(args.vendor))
    if args.write:
        PATCH.write_text(expected)
    elif PATCH.read_text() != expected:
        raise SystemExit("1010 patch drifted from pinned source generator")
    print("PASS: deterministic read-only 1010; no native compilation/device access")


if __name__ == "__main__":
    main()
