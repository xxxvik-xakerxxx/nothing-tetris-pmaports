#!/usr/bin/env python3
"""Generate the AP-tag-only util module overlay; never compile or use hardware."""
import argparse
import difflib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREFIX = 'drivers/misc/mediatek/ccci_util/'
MODE = 'CONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY'
SMEM = HERE.parent / 'runtime-smem'


def plan_sources(producer):
    """Reuse reviewed bodies, but compile no physical mapping/publication code."""
    sources = {name: (SMEM / name).read_text() for name in
               ('smem.c', 'smem.h', 'private.h', 'arguments.c', 'source_model.h')}
    smem = sources['smem.c']
    start = smem.index('static void unmap_private(')
    end = smem.index('static bool output_overlap(', start)
    smem = smem[:start] + smem[end:]
    start = smem.index('int tetris_smem_export_private(')
    end = smem.index('int tetris_smem_destroy(', start)
    smem = smem[:start] + smem[end:]
    smem = producer.replace(smem, '\tunmap_private(owner);\n', '')
    sources['smem.c'] = smem
    return {PREFIX + 'tetris_runtime_smem/' + name: source
            for name, source in sources.items()}


def candidate():
    spec = importlib.util.spec_from_file_location('packaged_metadata', HERE / 'check_metadata.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(vendor):
    producer = candidate()
    patch, before = producer.build(vendor)
    with tempfile.TemporaryDirectory(prefix='metadata-package-source-') as temp:
        root = Path(temp)
        for name, source in before.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        subprocess.run(['git', 'apply', '--check', '-'], input=patch, text=True,
                       cwd=root, check=True, capture_output=True)
        subprocess.run(['git', 'apply', '-'], input=patch, text=True,
                       cwd=root, check=True, capture_output=True)
        after = {str(path.relative_to(root)): path.read_text()
                 for path in (root / PREFIX).iterdir() if path.is_file()}
    for name in after:
        after[name] = after[name].replace('CONFIG_MTK_ECCCI_TETRIS_OWNER', MODE)
    owned = PREFIX + 'owned_tags.h'
    after[owned] = producer.replace(after[owned], 'static unsigned char *tetris_owned_tags;',
        'static struct tetris_metadata_banks tetris_owned_banks;\n'
        'static unsigned char *tetris_owned_tags;')
    after[owned] = producer.replace(after[owned], '\ttetris_owned_tags = snapshot;',
        '\ttetris_owned_banks = *banks;\n\ttetris_owned_tags = snapshot;')
    after[owned] += ('\n/* Copy only during serialized util init, not an NS access grant. */\n'
        'int mtk_ccci_owned_banks_copy(struct tetris_metadata_banks *out)\n{\n'
        '\tif (!out)\n\t\treturn -EINVAL;\n'
        '\tif (!s_init_done || !tetris_owned_tags)\n\t\treturn -ENODATA;\n'
        '\t*out = tetris_owned_banks;\n\treturn 0;\n}\n')
    after.update(plan_sources(producer))
    after[PREFIX + 'owned_smem_plan.c'] = (HERE / 'owned_smem_plan.c').read_text()
    makefile = PREFIX + 'Makefile'
    before[makefile] = producer.stock(vendor, 'Makefile')
    after[makefile] = producer.replace(before[makefile], '\t\t\tccci_util_md_mem.o',
        '\t\t\tccci_util_md_mem.o \\\n'
        '\t\t\towned_smem_plan.o \\\n'
        '\t\t\ttetris_runtime_smem/arguments.o \\\n'
        '\t\t\ttetris_runtime_smem/smem.o')
    after[makefile] += ('\nccflags-y += -I$(src)\n'
        'ccflags-y += -I$(DEVICE_MODULES_PATH)/drivers/misc/mediatek/eccci/fsm\n')
    main = PREFIX + 'ccci_util_lib_main.c'
    after[main] = producer.replace(after[main],
        '#if IS_ENABLED(' + MODE + ')\n\tint ret;\n#endif\n'
        '\tccci_log_init();\n#if IS_ENABLED(' + MODE + ')\n'
        '\tret = mtk_ccci_args_key_val_init();\n\tif (ret)\n\t\treturn ret;\n'
        '\tret = ccci_util_fo_init();\n\tif (ret)\n\t\treturn ret;\n'
        '#else\n\tmtk_ccci_args_key_val_init();\n\tccci_util_fo_init();\n#endif',
        '#if IS_ENABLED(' + MODE + ')\n'
        '\tint ret = mtk_ccci_args_key_val_init();\n\n'
        '\tif (ret)\n\t\tgoto metadata_fail;\n'
        '\tret = ccci_util_fo_init();\n\tif (ret)\n\t\tgoto metadata_fail;\n'
        '\tret = mtk_ccci_owned_smem_init();\n\tif (ret)\n\t\tgoto metadata_fail;\n'
        '\tpr_info("Tetris CCCI: owned metadata imported; runtime transport disabled\\n");\n'
        '\treturn 0;\nmetadata_fail:\n\tmtk_ccci_owned_smem_cleanup();\n'
        '\tmtk_ccci_owned_args_cleanup();\n\treturn ret;\n#endif\n'
        '\tccci_log_init();\n\tmtk_ccci_args_key_val_init();\n\tccci_util_fo_init();')
    after[main] = producer.replace(after[main], 'subsys_initcall(ccci_util_init);',
        '#if IS_ENABLED(' + MODE + ')\n'
        'static void __exit ccci_util_metadata_exit(void)\n{\n'
        '\tmtk_ccci_owned_smem_cleanup();\n'
        '\tmtk_ccci_owned_args_cleanup();\n}\n'
        'module_exit(ccci_util_metadata_exit);\n#endif\n\n'
        'subsys_initcall(ccci_util_init);')
    args = PREFIX + 'ccci_util_boot_args.c'
    after[args] = producer.replace(after[args], 'int mtk_ccci_add_new_args(',
        '#if IS_ENABLED(' + MODE + ')\n'
        'void mtk_ccci_owned_args_cleanup(void)\n{\n\tunsigned int i;\n\n'
        '\ts_init_done = 0;\n'
        '\tmemset(&tetris_owned_banks, 0, sizeof(tetris_owned_banks));\n'
        '\tmemset(s_args_tbl, 0, sizeof(s_args_tbl));\n'
        '\ts_args_num = 0;\n\ts_curr_ptr = NULL;\n'
        '\ts_curr_buf_idx = 0;\n\ts_curr_buf_free = 0;\n'
        '\tfor (i = 0; i < ARRAY_SIZE(s_buf); i++) {\n'
        '\t\tkfree(s_buf[i]);\n\t\ts_buf[i] = NULL;\n\t}\n'
        '\tkfree(tetris_owned_tags);\n\ttetris_owned_tags = NULL;\n'
        '}\n#endif\n\nint mtk_ccci_add_new_args(')
    init_start = after[args].index('int mtk_ccci_args_key_val_init(void)')
    init_end = after[args].index('void mtk_ccci_dump_args_info(void)', init_start)
    init = after[args][init_start:init_end]
    init = producer.replace(init, '\treturn 0;\n}',
        '#if IS_ENABLED(' + MODE + ')\n\tof_node_put(node);\n#endif\n'
        '\treturn 0;\n}')
    after[args] = after[args][:init_start] + init + after[args][init_end:]
    header = PREFIX + 'ccci_util_lib_main.h'
    after[header] = producer.replace(after[header], '#define MAX_MD_NUM_AT_LK\t(4)',
        '#if IS_ENABLED(' + MODE + ')\n'
        'struct tetris_metadata_banks;\n'
        'int mtk_ccci_owned_banks_copy(struct tetris_metadata_banks *out);\n'
        'int mtk_ccci_owned_smem_init(void);\n'
        'void mtk_ccci_owned_smem_cleanup(void);\n'
        'void mtk_ccci_owned_args_cleanup(void);\n#endif\n\n'
        '#define MAX_MD_NUM_AT_LK\t(4)')
    result = []
    for name in sorted(after):
        old, new = before.get(name, ''), after[name]
        if old == new:
            continue
        result.append(f'diff --git a/{name} b/{name}\n')
        if not old:
            result.append('new file mode 100644\n')
        result.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='a/' + name if old else '/dev/null', tofile='b/' + name))
    return ''.join(result), after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--emit-patch', type=Path)
    parser.add_argument('--check-patch', type=Path)
    args = parser.parse_args()
    patch, _ = build(args.vendor)
    if args.emit_patch:
        args.emit_patch.write_text(patch)
    if args.check_patch and args.check_patch.read_text() != patch:
        parser.error('packaged metadata overlay differs from the reviewed producer')
    print('AP-tag-only util overlay matches; no compilation or runtime operation')


if __name__ == '__main__':
    main()
