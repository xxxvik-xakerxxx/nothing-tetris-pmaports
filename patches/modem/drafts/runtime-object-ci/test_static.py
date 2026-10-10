#!/usr/bin/env python3
"""Source-only tests. Never call a compiler or execute the ARM64 build."""
import ast
import contextlib
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from check_objects import HERE, ROOT, PREFIX, load, plan, review, stage_vendor, check_generated

VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', ROOT.parent /
    'android_kernel_device_modules_6.1_nothing_mt6878'))


def parent_patch_state(workflow):
    # Check one immutable snapshot, even if the parent edits its workflow concurrently.
    with tempfile.TemporaryDirectory(prefix='runtime-parent-static-') as temp:
        root = Path(temp)
        target = root / '.github/workflows/ci.yml'
        target.parent.mkdir(parents=True)
        target.write_text(workflow)
        command = ['git', 'apply', '--check']
        patch = str(HERE / 'PARENT-INTEGRATION.patch')
        forward = subprocess.run(command + [patch], cwd=root,
            capture_output=True, text=True)
        helper = 'python3 patches/modem/drafts/runtime-object-ci/check_objects.py'
        if forward.returncode == 0:
            if helper in workflow:
                raise ValueError('Unexpected helper before integration')
            return 'unapplied'
        reverse = subprocess.run(command + ['--reverse', patch], cwd=root,
            capture_output=True, text=True)
        if reverse.returncode:
            raise ValueError('Integration drift: neither forward nor reverse check passes')
        block = (
            r"(?m)^(?P<indent> +)if \[ '\$\{\{ inputs\.research_owner_smoke \}\}' = true \]; then\n"
            r"(?P=indent)  python3 ci/kernel-object-smoke\.py --research-owners\n"
            r"(?P=indent)  " + re.escape(helper) + r"\n"
            r"(?P=indent)else\n"
            r"(?P=indent)  python3 ci/kernel-object-smoke\.py\n"
            r"(?P=indent)fi$")
        if workflow.count(helper) != 1 or len(re.findall(block, workflow)) != 1:
            raise ValueError('Helper must occur exactly once inside the research branch')
        return 'applied'


class ObjectTests(unittest.TestCase):
    def test_generation_mismatch_preserved_not_relaxed(self):
        with tempfile.TemporaryDirectory() as temp:
            diagnostics = Path(temp) / 'diagnostics'
            manifest = {}
            check_generated('prepare', 'same\n', 'same\n', diagnostics, manifest)
            self.assertFalse(diagnostics.exists())
            for generated in ('changed\n', 'same\nextra\n', ''):
                with self.subTest(generated=generated):
                    with self.assertRaisesRegex(ValueError, 'exact diagnostic diff'):
                        check_generated('prepare', generated, 'same\n', diagnostics, manifest)
                    self.assertEqual((diagnostics / 'prepare.generated.patch').read_text(), generated)
                    self.assertEqual((diagnostics / 'prepare.frozen.patch').read_text(), 'same\n')
                    self.assertTrue((diagnostics / 'prepare.diff').read_text())
                    record = manifest['generation_reviews']['prepare']
                    self.assertEqual(record['status'], 'failed')
                    self.assertNotEqual(record['generated_sha256'], record['frozen_sha256'])

    def test_python_syntax(self):
        for path in HERE.glob('*.py'):
            ast.parse(path.read_text())

    def test_manifest_exact_production_sources(self):
        data, _, _ = plan()
        names = set(subprocess.check_output(['git', '-C', str(VENDOR), 'ls-tree',
            '-r', '--name-only', data['vendor_commit']], text=True).splitlines())
        added = {PREFIX + 'eccci/fsm/ccci_tetris_owner.c',
                 PREFIX + 'eccci/hif/ccci_tetris_hif_owned.c'}
        self.assertEqual(sum(map(len, data['objects'].values())), 64)
        for root, objects in data['objects'].items():
            self.assertIn(PREFIX + root + '/Makefile', names)
            for name in objects:
                self.assertIn(PREFIX + root + '/' + str(Path(name).with_suffix('.c')), names | added)

    def test_frozen_sources_and_generated_patch_identity(self):
        prepare = load('static_runtime_prepare', HERE.parent / 'runtime-prepare/check_prepare.py')
        generated, before, after = prepare.build(VENDOR)
        self.assertEqual(generated, (HERE.parent / 'runtime-prepare/runtime-prepare.patch.vendor').read_text())
        core = PREFIX + 'eccci/'
        self.assertIn('ccci_tetris_owner_entry();', before[core + 'fsm/ccci_fsm.c'])
        self.assertIn('ccci_tetris_register_prepared', after[core + 'fsm/register_prepare.h'])
        self.assertIn('class_create("ccci_node")', after[core + 'ccci_core.c'])
        for name in ('runtime-ports', 'runtime-prepare', 'runtime-lifecycle'):
            review(HERE.parent / name)

    def test_review_drift_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'REVIEW.sha256').write_text('0' * 64 + '  actual.c\n')
            (root / 'actual.c').write_text('changed\n')
            with self.assertRaises(ValueError):
                review(root)

    def test_parent_patch_application(self):
        parent_patch_state((ROOT / '.github/workflows/ci.yml').read_text())

    def test_parent_patch_states_and_drift(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        state = parent_patch_state(workflow)
        with tempfile.TemporaryDirectory(prefix='runtime-parent-cases-') as temp:
            root = Path(temp)
            target = root / '.github/workflows/ci.yml'
            target.parent.mkdir(parents=True)
            target.write_text(workflow)
            patch = str(HERE / 'PARENT-INTEGRATION.patch')
            if state == 'applied':
                subprocess.run(['git', 'apply', '--reverse', patch], cwd=root, check=True)
            baseline = target.read_text()
            self.assertEqual(parent_patch_state(baseline), 'unapplied')
            subprocess.run(['git', 'apply', patch], cwd=root, check=True)
            applied = target.read_text()
            self.assertEqual(parent_patch_state(applied), 'applied')
        helper = 'python3 patches/modem/drafts/runtime-object-ci/check_objects.py'
        helper_line = next(line for line in applied.splitlines(True) if helper in line)
        mutations = (
            applied.replace(helper_line, ''),
            applied + helper_line,
            applied.replace(helper_line, '').replace(
                '            python3 ci/kernel-object-smoke.py\n',
                '            python3 ci/kernel-object-smoke.py\n' + helper_line),
            applied.replace('--research-owners', '--wrong-owners'),
            applied.replace('linux-headers git', 'linux-headers'),
        )
        for mutated in mutations:
            with self.subTest(workflow=mutated):
                with self.assertRaises(ValueError):
                    parent_patch_state(mutated)

    def test_full_shipping_source_stack(self):
        # Source-only archive/patch check; never invokes make or a C compiler.
        data, _, package = plan()
        with tempfile.TemporaryDirectory(prefix='runtime-stack-static-') as temp:
            with contextlib.redirect_stdout(io.StringIO()):
                stage_vendor(VENDOR, Path(temp) / 'vendor', package, data)
            self.assertEqual(set(data['overlays_sha256']),
                {'owner', 'runtime-ports', 'runtime-prepare', 'runtime-lifecycle'})
            lifecycle = load('static_lifecycle_actual_bytes', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
            _, _, expected = lifecycle.build(VENDOR)
            self.assertEqual((Path(temp) / 'vendor' / lifecycle.SOURCE).read_text(), expected)
            self.assertEqual(data['lifecycle_source_sha256'],
                data['compiled_source_sha256'][lifecycle.SOURCE])
            for root, objects in data['objects'].items():
                for name in objects:
                    source = PREFIX + root + '/' + str(Path(name).with_suffix('.c'))
                    self.assertIn(source, data['compiled_source_sha256'])

    def test_compile_rejected_outside_ci(self):
        env = dict(os.environ, CI='false', GITHUB_ACTIONS='false')
        result = subprocess.run(['python3', '-B', str(HERE / 'check_objects.py')],
            env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('GitHub CI-only', result.stderr)

    def test_native_callback_runner_rejected_outside_ci(self):
        env = dict(os.environ, CI='false', GITHUB_ACTIONS='false')
        result = subprocess.run(['python3', '-B', str(HERE / 'check_native_callbacks.py'),
            '--vendor', str(VENDOR)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('GitHub CI-only', result.stderr)


if __name__ == '__main__':
    unittest.main()
