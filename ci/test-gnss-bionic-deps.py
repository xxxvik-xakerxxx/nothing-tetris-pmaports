#!/usr/bin/env python3
"""Source and admission checks; no compiler or target execution."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('bionic_deps', HERE / 'build-gnss-bionic-deps.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DependencyTests(unittest.TestCase):
    def test_local_c_build_denied(self):
        result = subprocess.run([sys.executable, '-B', str(HERE / 'build-gnss-bionic-deps.py'),
            '--ndk', '/unused', '--work', '/unused', '--prefix', '/unused'],
            env=dict(os.environ, CI='false', GITHUB_ACTIONS='false'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('GitHub CI-only', result.stderr)

    def test_archive_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in ('source/file', '../escape', '/source/file', 'wrong/file'):
                archive = directory / 'source.tar'
                with tarfile.open(archive, 'w') as stream:
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    stream.addfile(member, io.BytesIO(b'x'))
                if name == 'source/file':
                    self.assertEqual(MODULE.extract(archive, directory, 'source'), directory / 'source')
                else:
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        MODULE.extract(archive, directory, 'source')

    def test_real_elf_export_and_dependencies(self):
        header = 'Machine: AArch64\nType: DYN\n'
        symbols = '1: 0 32 FUNC GLOBAL DEFAULT 1 EVP_Digest@@OPENSSL_3.0.0\n'
        dynamic = '(NEEDED) Shared library: [libc.so]\n'
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / 'library.so'
            library.write_bytes(b'fixture')
            for h, d, s, valid in ((header, dynamic, symbols, True),
                (header.replace('AArch64', 'X86-64'), dynamic, symbols, False),
                (header, dynamic, symbols.replace('DEFAULT 1', 'DEFAULT UND'), False),
                (header, dynamic.replace('libc.so', 'libc.so.6'), symbols, False),
                (header, dynamic, symbols + ' GLIBC_2.17', False)):
                with patch.object(MODULE.subprocess, 'check_output', side_effect=[h, d, s]):
                    if valid:
                        self.assertEqual(MODULE.library_identity(Path('/unused'), library,
                            'EVP_Digest')['needed'], ['libc.so'])
                    else:
                        with self.assertRaises(ValueError):
                            MODULE.library_identity(Path('/unused'), library, 'EVP_Digest')

    def test_empty_archive_and_link_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            archive = directory / 'source.tar'
            with tarfile.open(archive, 'w'):
                pass
            with self.assertRaises(ValueError):
                MODULE.extract(archive, directory, 'source')
            with tarfile.open(archive, 'w') as stream:
                member = tarfile.TarInfo('source/link')
                member.type = tarfile.SYMTYPE
                member.linkname = '../../escape'
                stream.addfile(member)
            with self.assertRaises(tarfile.FilterError):
                MODULE.extract(archive, directory, 'source')


if __name__ == '__main__':
    unittest.main()
