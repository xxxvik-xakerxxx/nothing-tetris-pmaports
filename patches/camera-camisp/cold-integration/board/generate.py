#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source-backed board caller delta atop frozen cold integration; no compiler."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FROZEN_PATCH = '8fbf0a52a41483dc11fb127dd65bd68020c274579d25aeb004478bc8978a90ec'
spec = importlib.util.spec_from_file_location('frozen_cold_gen', HERE.parent / 'generate.py')
cold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cold)
DEST = cold.DIR + 'board/'
DT = 'arch/arm64/boot/dts/mediatek/tetris-cold-root-disabled.dtsi'
BINDING = 'Documentation/devicetree/bindings/media/nothing,tetris-cold-camsv0.yaml'
SOURCES = ('mt6878-cold-board.c', 'mt6878-cold-board.h', 'Kconfig', 'Makefile',
           'tetris-cold-root-disabled.dtsi', 'nothing,tetris-cold-camsv0.yaml')
VENDOR_DEVICE = ('arch/arm64/boot/dts/mediatek/mt6878.dts',
                 'arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi')
VENDOR_MODULES = ('mtkcam/camsys/isp7sp/cam/mtk_cam-job.c',
                  'mtkcam/camsys/isp7sp/cam/mtk_cam-job_utils.c',
                  'mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c',
                  'mtkcam/imgsensor/src-v4l2/common/imx882txd_mipi_raw/imx882txdmipiraw_Sensor.c')
LINUX = ('include/dt-bindings/clock/mediatek,mt6878-clock.h',
         'arch/arm64/boot/dts/mediatek/mt6878.dtsi', 'drivers/base/dd.c',
         'drivers/base/platform.c', 'drivers/base/power/common.c')
SUPPLIERS = 'patches/camera-camisp/resources/mt6878-camisp-supplier-resources-disabled.dtsi'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def vendor(repo, pin, paths, prefix, evidence):
    result = {}
    for path in paths:
        data = subprocess.check_output(['git', '-C', str(repo), 'show', pin + ':' + path])
        blob = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', pin + ':' + path], text=True).strip()
        key = prefix + path
        result[key] = data.decode()
        evidence[key] = {'commit': pin, 'blob': blob, 'sha256': sha(data)}
    return result


def verify_vendor(sources):
    device = sources['device:' + VENDOR_DEVICE[0]]
    node = cold.block(device, 'camsv1@1a100000')
    fixture = (HERE / 'tetris-cold-root-disabled.dtsi').read_text()
    original_reg = re.search(r'\breg\s*=\s*([^;]+);', node)[1]
    actual_reg = re.search(r'\breg\s*=\s*([^;]+);', fixture)[1]
    source_cells = [list(map(lambda n: int(n, 0), group.split())) for group in re.findall(r'<([^>]+)>', original_reg)]
    native_cells = [list(map(lambda n: int(n, 0), group.split())) for group in re.findall(r'<([^>]+)>', actual_reg)]
    if any(len(cells) != 4 or cells[0] or cells[2] for cells in source_cells) or \
            native_cells != [[cells[1], cells[3]] for cells in source_cells]:
        raise ValueError('NOS resource mismatch: reg native one-address/one-size translation')
    for property in ('reg-names', 'clock-names'):
        pattern = r'\b' + re.escape(property) + r'\s*=\s*([^;]+);'
        original = re.search(pattern, node)[1]
        actual = re.search(pattern, fixture)[1]
        if re.sub(r'\s+', '', original) != re.sub(r'\s+', '', actual):
            raise ValueError('NOS resource mismatch: ' + property)
    original_irqs = re.findall(r'<GIC_SPI (\d+) IRQ_TYPE_LEVEL_HIGH 0>', node)
    actual_irqs = re.findall(r'<GIC_SPI (\d+) IRQ_TYPE_LEVEL_HIGH 0>', fixture)
    if original_irqs != actual_irqs or len(actual_irqs) != 4:
        raise ValueError('NOS four-IRQ route mismatch')
    original_clocks = re.findall(r'<&\w+ (CLK_\w+)>', re.search(r'\bclocks\s*=\s*([^;]+);', node)[1])
    actual_clocks = re.findall(r'<&\w+ (CLK_\w+)>', re.search(r'\bclocks\s*=\s*([^;]+);', fixture)[1])
    if original_clocks != actual_clocks:
        raise ValueError('NOS clock identity/order mismatch')
    camera = sources['device:' + VENDOR_DEVICE[1]]
    port = cold.block(camera, 'seninf_csi_port_1:')
    if 'csi-port = "1";' not in port or 'remote-endpoint = <&sensor0_out>;' not in port:
        raise ValueError('NOS main-sensor CSI-port evidence changed')
    sensor = cold.block(camera, 'sensor0: sensor0@1a')
    if 'sensor-names = "imx882_mipi_raw", "imx882txd_mipi_raw";' not in sensor:
        raise ValueError('NOS sensor0 IMX882 variant mapping changed')
    job = sources['modules:' + VENDOR_MODULES[0]]
    # The first occurrence is a forward declaration; use the last definition.
    only_sv = cold.function(job[job.rindex('static int mtk_cam_job_fill_ipi_config_only_sv('):],
                            'static int mtk_cam_job_fill_ipi_config_only_sv(')
    if 'config->flags = MTK_CAM_IPI_CONFIG_TYPE_INIT;' not in only_sv or \
            'job->ipi_config.sv_input[0][i].input' not in only_sv:
        raise ValueError('NOS producer-config provenance changed')
    utils = sources['modules:' + VENDOR_MODULES[1]]
    for anchor in ('sv_sink = &job->req->sv_data[sv_pipe_idx].sink;',
                   'sv_sink->width, sv_sink->height,', 'sv_sink->mbus_code, sv_pipe'):
        if anchor not in utils:
            raise ValueError('NOS per-request sink source changed: ' + anchor)
    for path in VENDOR_MODULES[2:]:
        descriptor = cold.function(sources['modules:' + path], 'static struct mtk_mbus_frame_desc_entry frame_desc_prev[]')
        if 'MTK_MBUS_FRAME_DESC_REMAP_TO_RAW10' not in descriptor or 'VC_PDAF_STATS' not in descriptor:
            raise ValueError('NOS PDAF remap contract changed: ' + path)


def build(archive, device_repo, modules_repo):
    if sha((HERE.parent / 'cold-integration.patch').read_bytes()) != FROZEN_PATCH:
        raise ValueError('frozen cold integration changed; require reviewed parent profile')
    base, frozen, patch, before = cold.build(archive, device_repo, modules_repo)
    if sha(patch.encode()) != FROZEN_PATCH:
        raise ValueError('source/package profile no longer reproduces frozen cold patch')
    base.update(frozen)
    evidence = {'kernel_commit': cold.KERNEL, 'device_commit': cold.DEVICE,
                'modules_commit': cold.MODULES, 'frozen_patch_sha256': FROZEN_PATCH,
                'kernel_archive_sha512': before['kernel_archive_sha512'], 'vendor': {}}
    subprocess.check_output(['git', 'ls-files', '--error-unmatch', SUPPLIERS], cwd=ROOT)
    suppliers = (ROOT / SUPPLIERS).read_text()
    evidence['supplier_fixture'] = {'path': SUPPLIERS, 'sha256': sha(suppliers.encode())}
    for label, contract in (('camisp_l14:', 'mediatek,larb-id = <14>;'),
                            ('cam_main:', 'reg = <0x1a000000 0x1000>;'),
                            ('smi_cam_vcore_2x1_sub_comm0:', 'mediatek,common-id = <31>;')):
        node = cold.block(suppliers, label)
        if contract not in node or 'status = "disabled";' not in node:
            raise ValueError('tracked supplier topology no longer matches board reference: ' + label)
    sources = vendor(device_repo, cold.DEVICE, VENDOR_DEVICE, 'device:', evidence['vendor'])
    sources.update(vendor(modules_repo, cold.MODULES, VENDOR_MODULES, 'modules:', evidence['vendor']))
    verify_vendor(sources)
    linux = {}
    with tarfile.open(archive, 'r|gz') as source:
        for member in source:
            path = member.name.removeprefix('linux-' + cold.KERNEL + '/')
            if member.isfile() and path in LINUX:
                linux[path] = source.extractfile(member).read().decode()
    if set(linux) != set(LINUX):
        raise ValueError('missing pinned native framework inputs')
    evidence['native_framework_sha256'] = {p: sha(t.encode()) for p, t in linux.items()}
    output = {DEST + name: (HERE / name).read_text() for name in SOURCES[:4]}
    output[DT] = (HERE / SOURCES[4]).read_text()
    output[BINDING] = (HERE / SOURCES[5]).read_text()
    output[cold.DIR + 'Makefile'] = base[cold.DIR + 'Makefile'] + '\nobj-$(CONFIG_VIDEO_MT6878_COLD_BOARD) += board/\n'
    output[cold.DIR + 'Kconfig'] = base[cold.DIR + 'Kconfig'] + '\nsource "' + DEST + 'Kconfig"\n'
    patch = cold.delta(base, output)
    with tempfile.TemporaryDirectory(prefix='cold-board-apply-') as directory:
        tree = Path(directory)
        for path, text in base.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        candidate = tree / 'board-owner.patch'
        candidate.write_text(patch)
        cold.stream.run(['git', 'apply', '--check', str(candidate)], tree)
        cold.stream.run(['git', 'apply', str(candidate)], tree)
        for path, text in output.items():
            if (tree / path).read_text() != text:
                raise ValueError('applied board payload mismatch: ' + path)
    evidence.update(baseline_sha256={p: sha(t.encode()) for p, t in base.items()},
                    payload_sha256={p: sha(t.encode()) for p, t in output.items()}, patch_sha256=sha(patch.encode()),
                    template_sha256={p: sha((HERE / p).read_bytes()) for p in SOURCES})
    return base, output, linux, sources, patch, evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    cold.stream.arguments(parser)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    _, _, _, _, patch, evidence = build(args.kernel_archive, args.device_repo, args.modules_repo)
    for name, data in {'board-owner.patch': patch, 'evidence.json': json.dumps(evidence, indent=2, sort_keys=True) + '\n'}.items():
        if args.write:
            (HERE / name).write_text(data)
        elif (HERE / name).read_text() != data:
            raise ValueError('stale board output: ' + name)
    print('PASS: pinned NOS board/producer inputs and strict post-cold board patch application; no compilation')
