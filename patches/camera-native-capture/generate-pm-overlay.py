#!/usr/bin/env python3
"""Emit isolated review overlays; never edit frozen sources or compile C."""
import argparse
import difflib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def replace(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)


def apply_overlay(source, path, patch):
    lines = source.splitlines(True)
    body = patch.split('+++ b/' + path + '\n', 1)[1].split('\n--- a/', 1)[0]
    if not body.endswith('\n'):
        body += '\n'
    result, cursor = [], 0
    for hunk in re.split(r'^@@ ', body, flags=re.M)[1:]:
        header, content = hunk.split('\n', 1)
        start = int(re.match(r'-(\d+)', header).group(1)) - 1
        result += lines[cursor:start]
        cursor = start
        for line in content.splitlines(True):
            if line.startswith((' ', '-')):
                assert lines[cursor] == line[1:], (path, cursor)
                cursor += 1
            if line.startswith((' ', '+')):
                result.append(line[1:])
    return ''.join(result + lines[cursor:])


def outputs():
    lifecycle = (ROOT / 'camera-seninf-controller/native-bind.patch').read_text()
    path = 'mt6878-seninf-graph.c'
    old = apply_overlay((ROOT / 'camera-seninf' / path).read_text(), path, lifecycle)
    new = replace(old, '#include "mt6878-seninf-controller.h"',
                  '#include "mt6878-seninf-controller.h"\n'
                  '#include "mt6878-seninf-pm.h"\n'
                  '#include "mt6878-native-capture.h"')
    new = replace(new, '\tunsigned int csi_port;\n',
                  '\tunsigned int csi_port;\n\tstruct mt6878_seninf_pm native_pm;\n')
    marker = '\tendpoint = fwnode_graph_get_endpoint_by_id(dev_fwnode(dev), SENINF_SINK, 0, 0);'
    new = replace(new, marker,
                  '\tret = mt6878_seninf_pm_init(&receiver->native_pm, dev,\n'
                  '\t\treceiver->domains, receiver->clocks, ARRAY_SIZE(receiver->clocks),\n'
                  '\t\treceiver->vcore, receiver->csi_port);\n'
                  '\tif (ret)\n\t\treturn dev_err_probe(dev, ret, "SENINF PM providers unavailable\\n");\n'
                  + marker)
    new = replace(new, '''	/* The graph skeleton cannot power a PHY without audited DVFS/mux logic. */
	return -EOPNOTSUPP;''', '''	struct mt6878_seninf *receiver = dev_get_drvdata(dev);

	return mt6878_seninf_pm_resume(&receiver->native_pm);''')
    marker = '''static int mt6878_seninf_runtime_suspend(struct device *dev)
{
	return 0;
}'''
    new = replace(new, marker, '''static int mt6878_seninf_runtime_suspend(struct device *dev)
{
	struct mt6878_seninf *receiver = dev_get_drvdata(dev);

	/* Allocated controller retains the PM usage ref through failed cleanup. */
	if (v4l2_get_subdev_hostdata(&receiver->sd))
		return -EBUSY;
	return mt6878_seninf_pm_suspend(&receiver->native_pm);
}''')
    bind = '''int mt6878_seninf_native_bind(struct mt6878_seninf_controller *c,
	struct mt6878_camsv_platform *capture)
{
	struct mt6878_seninf *receiver;

	if (!capture || !capture->receiver || !capture->origin ||
	    capture->receiver->ops != &mt6878_seninf_ops)
		return -EINVAL;
	receiver = to_seninf(capture->receiver);
	if (receiver->sensor != capture->sensor ||
	    receiver->sensor_pad != capture->origin->index)
		return -ENOLINK;
	return mt6878_seninf_controller_bind(c, to_platform_device(receiver->sd.dev),
		capture, receiver->base, receiver->analog, receiver->clocks,
		ARRAY_SIZE(receiver->clocks), receiver->domains, receiver->vcore,
		receiver->clocks[3 + receiver->csi_port].clk, &receiver->cphy,
		receiver->sensor_pad);
}

void __iomem *mt6878_seninf_native_base(struct v4l2_subdev *sd)
{
	if (!sd || sd->ops != &mt6878_seninf_ops)
		return NULL;
	return to_seninf(sd)->base;
}

'''
    new = replace(new, 'static void mt6878_seninf_remove(', bind + 'static void mt6878_seninf_remove(')
    new = replace(new, '\t\t.name = "mt6878-seninf-graph",',
                  '\t\t.name = "mt6878-seninf-graph",\n\t\t.suppress_bind_attrs = true,')
    new = replace(new, 'resource/graph candidate registered; hardware streaming unavailable',
                  'native SENINF candidate registered; activation remains board-gated')
    result = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                       fromfile='a/' + path, tofile='b/' + path))

    path = 'mt6878-seninf-controller.c'
    old = (ROOT / 'camera-seninf-controller' / path).read_text()
    new = replace(old, '''	for (i = 0; i < c->num_clocks; i++)
		if (!__clk_is_enabled(c->clocks[i].clk))
			return -EHOSTDOWN;''', '''	/* Vendor enables CAM gates, CAMTM and selected CSI, not unused muxes
	 * or all possible PLL sources. The selected mux holds its parent ref.
	 */
	for (i = 0; i < 3; i++)
		if (!__clk_is_enabled(c->clocks[i].clk))
			return -EHOSTDOWN;
	if (!__clk_is_enabled(c->clocks[7].clk) || !__clk_is_enabled(c->route.csi_clock))
		return -EHOSTDOWN;''')
    new = replace(new, 'voltage < c->dvfs[5] || voltage > c->dvfs[6]',
                  'voltage < c->dvfs[5]')
    # No DMA attempt is a real ownership observation, not fake quiescence.
    new = new.replace('c->capture->direct->pair.tx.quiesced',
                      '(!c->capture->direct->pair.tx.hw_attempted ||\n'
                      '\t\t\tc->capture->direct->pair.tx.quiesced)')
    result += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile='a/' + path, tofile='b/' + path))

    path = 'mt6878-camsv-platform.c'
    old = apply_overlay((ROOT / 'camera-direct-platform' / path).read_text(), path, lifecycle)
    new = replace(old, '#include "mt6878-camsv-platform.h"',
                  '#include "mt6878-camsv-platform.h"\n#include "mt6878-native-capture.h"')
    new = replace(new, 'ret = v4l2_subdev_disable_streams(p->receiver, 1, 1);',
                  'ret = mt6878_native_capture_receiver_stop(p);')
    result += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile='a/' + path, tofile='b/' + path))
    path = 'mt6878-camsv-platform.h'
    old = (ROOT / 'camera-direct-platform' / path).read_text()
    new = replace(old, 'struct mt6878_camsv_platform;\n',
                  'struct mt6878_camsv_platform;\nstruct mt6878_native_capture;\n')
    new = replace(new, '\tstruct mt6878_camsv_direct *direct;\n',
                  '\tstruct mt6878_camsv_direct *direct;\n'
                  '\tstruct mt6878_native_capture *native_capture;\n')
    result += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile='a/' + path, tofile='b/' + path))
    return {'native-pm.patch': result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    generated = outputs()
    if args.check:
        for name, content in generated.items():
            assert (HERE / name).read_text() == content, name
        print('PASS deterministic native PM overlay')
    else:
        json.dump(generated, sys.stdout)


if __name__ == '__main__':
    main()
