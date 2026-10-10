#!/usr/bin/env python3
"""Generate NEW review overlays; never modify frozen sources or build C."""
import argparse
import difflib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def replace(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new)


def diff(path, old, new):
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                      fromfile='a/' + path, tofile='b/' + path))


def sensor_source():
    patch = (ROOT.parent / 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878/'
             '0112-media-i2c-imx882-v4l2-controls.patch').read_text()
    marker = '+++ b/drivers/media/i2c/imx882-tetris-stream.c\n'
    body = patch.split(marker, 1)[1].split('\ndiff --git ', 1)[0]
    return ''.join(line[1:] for line in body.splitlines(True) if line.startswith('+'))


def outputs():
    old = sensor_source()
    new = replace(old, 'format->which == V4L2_SUBDEV_FORMAT_ACTIVE && camera->streaming)',
                  'format->which == V4L2_SUBDEV_FORMAT_ACTIVE &&\n'
                  '\t    (camera->streaming || media_entity_pipeline(&sd->entity)))')
    new = replace(new, 'static int imx882_stream(struct v4l2_subdev *sd, int enable)',
                  'static int imx882_stream_locked(struct v4l2_subdev *sd, int enable)')
    start = new.index('static int imx882_stream_locked')
    end = new.index('static const struct v4l2_subdev_video_ops', start)
    block = new[start:end]
    block = replace(block, '\tmutex_lock(&camera->lock);',
                    '\tlockdep_assert_held(&camera->lock);')
    block = replace(block, '\tmutex_unlock(&camera->lock);\n', '')
    new = new[:start] + block + new[end:]
    callbacks = '''static int imx882_enable_streams(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	(void)state;
	if (pad || mask != 1)
		return -EINVAL;
	return imx882_stream_locked(sd, 1);
}

static int imx882_disable_streams(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	(void)state;
	if (pad || mask != 1)
		return -EINVAL;
	return imx882_stream_locked(sd, 0);
}

static int imx882_power(struct v4l2_subdev *sd, int on)
{
	struct imx882_camera *camera = to_imx882(sd);
	int ret;

	if (on)
		return -EOPNOTSUPP; /* Stream enable owns the complete power sequence. */
	mutex_lock(&camera->lock);
	/* Initial stopped-state cleanup, not a caller-provided readiness bit.
	 * Cannot discharge an active stream or its native V4L2 bookkeeping.
	 */
	ret = v4l2_subdev_is_streaming(sd) ? -EBUSY : imx882_stop(camera);
	mutex_unlock(&camera->lock);
	return ret;
}

'''
    new = replace(new, 'static const struct v4l2_subdev_video_ops imx882_video_ops',
                  callbacks + 'static const struct v4l2_subdev_video_ops imx882_video_ops')
    new = replace(new, '\t.s_stream = imx882_stream,',
                  '\t.s_stream = v4l2_subdev_s_stream_helper,')
    new = replace(new, 'static const struct v4l2_subdev_ops imx882_subdev_ops = {',
                  'static const struct v4l2_subdev_core_ops imx882_core_ops = {\n'
                  '\t.s_power = imx882_power,\n};\n\n'
                  'static const struct v4l2_subdev_ops imx882_subdev_ops = {\n'
                  '\t.core = &imx882_core_ops,')
    new = replace(new, '\t.enum_mbus_code = imx882_enum_code,',
                  '\t.enable_streams = imx882_enable_streams,\n'
                  '\t.disable_streams = imx882_disable_streams,\n'
                  '\t.enum_mbus_code = imx882_enum_code,')
    sensor = diff('drivers/media/i2c/imx882-tetris-stream.c', old, new)

    old = (ROOT / 'camera-seninf/mt6878-seninf-graph.c').read_text()
    new = replace(old, '#include "mt6878-seninf-contract.h"',
                  '#include "mt6878-seninf-contract.h"\n'
                  '#include "mt6878-seninf-controller.h"')
    begin = new.index('static int mt6878_seninf_set_format(')
    end = new.index('static int mt6878_seninf_check_sensor(', begin)
    block = replace(new[begin:end], '\tsink = v4l2_subdev_state_get_format(state, SENINF_SINK);',
                  '\tif (format->which == V4L2_SUBDEV_FORMAT_ACTIVE &&\n'
                  '\t    media_entity_pipeline(&sd->entity))\n'
                  '\t\treturn -EBUSY;\n'
                  '\tsink = v4l2_subdev_state_get_format(state, SENINF_SINK);')
    new = new[:begin] + block + new[end:]
    begin = new.index('static int mt6878_seninf_stream(')
    end = new.index('static const struct v4l2_subdev_pad_ops', begin)
    new = new[:begin] + new[end:]
    new = replace(new, '\t.get_fmt = v4l2_subdev_get_fmt,',
                  '\t.enable_streams = mt6878_seninf_controller_enable,\n'
                  '\t.disable_streams = mt6878_seninf_controller_disable,\n'
                  '\t.get_fmt = v4l2_subdev_get_fmt,')
    new = replace(new, '\t.s_stream = mt6878_seninf_stream,',
                  '\t.s_stream = v4l2_subdev_s_stream_helper,')
    overlays = diff('mt6878-seninf-graph.c', old, new)
    old = (ROOT / 'camera-seninf-route/mt6878-seninf-route.c').read_text()
    # Two stop sites: replace ONLY initial prepare; do not alter frozen legacy
    # source_off function, which this native controller does not invoke.
    needle = '\tret = v4l2_subdev_call(r->sensor, video, s_stream, 0);\n'
    begin = old.index('int mt6878_seninf_route_prepare(')
    end = old.index('int mt6878_seninf_route_matches(', begin)
    block = replace(old[begin:end], needle,
                  '\tret = v4l2_subdev_call(r->sensor, core, s_power, 0);\n')
    new = old[:begin] + block + old[end:]
    overlays += diff('mt6878-seninf-route.c', old, new)
    old = (ROOT / 'camera-direct-platform/mt6878-camsv-platform.c').read_text()
    new = replace(old, '''		ret = v4l2_subdev_call(p->sensor, video, s_stream, 0);
		if (ret)
			first = ret;
		ret = v4l2_subdev_call(p->receiver, video, s_stream, 0);
		if (ret && !first)
			first = ret;''', '''		/* Receiver owns native sensor stop and SENINF IRQ/route retirement.
		 * Native disable retains enabled stream state on an actual failure.
		 */
		ret = v4l2_subdev_disable_streams(p->receiver, 1, 1);
		if (ret)
			first = ret;''')
    overlays += diff('mt6878-camsv-platform.c', old, new)
    old = (ROOT / 'camera-direct-hardware/mt6878-camsv-hardware.c').read_text()
    new = replace(old, '#include "mt6878-camsv-hardware.h"',
                  '#include "mt6878-camsv-hardware.h"\n'
                  '#include "mt6878-seninf-controller.h"')
    begin = new.index('\tcase MT6878_SV_ROUTE:')
    end = new.index('\tcase MT6878_SV_COMPOSER:', begin)
    new = new[:begin] + '''\tcase MT6878_SV_ROUTE:
\tcase MT6878_SV_STOPPED:
\t\treturn mt6878_seninf_controller_gate(
\t\t\tv4l2_get_subdev_hostdata(p->receiver), gate, job);
''' + new[end:]
    overlays += diff('mt6878-camsv-hardware.c', old, new)
    return {'imx882-native-streams.patch': sensor, 'native-bind.patch': overlays}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    generated = outputs()
    if args.check:
        for name, content in generated.items():
            assert (HERE / name).read_text() == content, name
        print('PASS deterministic lifecycle overlays; no frozen files changed')
    else:
        import json
        json.dump(generated, sys.stdout)


if __name__ == '__main__':
    main()
