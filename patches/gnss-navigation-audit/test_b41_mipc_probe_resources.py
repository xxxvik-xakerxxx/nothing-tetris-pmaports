"""Pinned executable admission evidence; never execute the probe or library."""
import errno
import ast
import fcntl
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from b41_mipc_probe_resources import (ProbeResources, ProbeXmlResources,
    PROBE_SHA, MNL_SHA, XML_SHA, XML_SIZE, XML_TARGET)
from test_b41_mipc_provider_resources import STOCK, BIONIC

XML_ROOT = Path(os.environ.get("TETRIS_B41_XML_ROOT",
    os.environ.get("TETRIS_B41_STOCK_ROOT", "/private/tmp/tetris-b41-port-assets-ci37941089972")))


def fake_probe_init(owner, _stock, _bionic):
    """Descriptor labels for ownership faults ONLY; never a successful backend."""
    owner.base = Mock(move=Mock(side_effect=[list(range(10)), OSError(errno.EINVAL, "moved")]))
    owner.extra = [71, 72]


def fake_xml_os():
    fake = Mock(open=Mock(return_value=77))
    for flag in ("O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        setattr(fake, flag, getattr(os, flag))
    fake.fstat.return_value.st_size = XML_SIZE
    return fake


class ProbeTests(unittest.TestCase):
    def test_xml_pin_and_target_match_real_asset_and_source_profile(self):
        raw = (XML_ROOT / XML_TARGET).read_bytes()
        self.assertEqual(len(raw), XML_SIZE)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), XML_SHA)
        profile = Path(__file__).with_name("xml-policy-draft") / "b41_xml_read_profile.py"
        constants = {node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(profile.read_text()).body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("XML_SHA", "PRIMARY")}
        self.assertEqual(constants["XML_SHA"], XML_SHA)
        self.assertEqual(constants["PRIMARY"], "/" + XML_TARGET)
        header = Path(__file__).with_name("b41_mipc_loader_root.h").read_text()
        self.assertIn(f'#define B41_MIPC_XML_TARGET "{XML_TARGET}"', header)
        self.assertIn(f'#define B41_MIPC_XML_SIZE {XML_SIZE}u', header)

    def test_xml_single_transfer_fixed_pin_path_and_readonly_mode(self):
        fake = fake_xml_os()
        with patch.object(ProbeResources, "__init__", fake_probe_init), \
                patch("b41_mipc_probe_resources.os", fake), \
                patch("b41_mipc_probe_resources.seal_provider", return_value=88) as seal:
            owned = ProbeXmlResources(STOCK, BIONIC, XML_ROOT)
            seal.assert_called_once_with(77, XML_SHA)
            fake.open.assert_called_once_with(XML_ROOT / XML_TARGET,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
            fake.fchmod.assert_called_once_with(88, 0o444)
            self.assertEqual(owned.move(), [*range(10), 71, 72, 88])
            owned.close()
            fake.close.assert_called_once_with(77)  # Moved copies not closed here.
            with self.assertRaises(OSError): owned.move()

    def test_xml_source_missing_releases_only_existing_owned_fds(self):
        fake = fake_xml_os()
        fake.open.side_effect = OSError(errno.ENOENT, "missing exact stock asset")
        with patch.object(ProbeResources, "__init__", fake_probe_init), \
                patch("b41_mipc_probe_resources.os", fake):
            with self.assertRaises(OSError) as caught:
                ProbeXmlResources(STOCK, BIONIC, XML_ROOT)
        self.assertEqual(caught.exception.errno, errno.ENOENT)
        self.assertEqual([call.args[0] for call in fake.close.call_args_list], [71, 72])

    def test_xml_pin_failure_keeps_first_when_source_and_base_cleanup_fail(self):
        fake = fake_xml_os()
        def close(fd):
            if fd == 77: raise OSError(errno.EIO, "source close")
        fake.close.side_effect = close
        def init(owner, stock, bionic):
            fake_probe_init(owner, stock, bionic)
            owner.base.close.side_effect = OSError(errno.EIO, "base close")
        with patch.object(ProbeResources, "__init__", init), \
                patch("b41_mipc_probe_resources.os", fake), \
                patch("b41_mipc_probe_resources.seal_provider", side_effect=OSError(errno.EBADMSG, "pin")):
            with self.assertRaises(OSError) as caught:
                ProbeXmlResources(STOCK, BIONIC, XML_ROOT)
        self.assertEqual(caught.exception.errno, errno.EBADMSG)
        self.assertIn("source close", caught.exception.__notes__[0])
        self.assertIn("base close", caught.exception.__notes__[1])

    def test_xml_size_and_mode_failure_close_copies_transactionally(self):
        for bad_size, bad_copy, mode_fault in ((True, False, False),
                                               (False, True, False), (False, False, True)):
            fake = fake_xml_os()
            if bad_size: fake.fstat.return_value.st_size = XML_SIZE + 1
            if bad_copy:
                fake.fstat.side_effect = [SimpleNamespace(st_size=XML_SIZE),
                                         SimpleNamespace(st_size=XML_SIZE + 1)]
            if mode_fault: fake.fchmod.side_effect = OSError(errno.EROFS, "mode")
            with self.subTest(bad_size=bad_size, bad_copy=bad_copy), \
                    patch.object(ProbeResources, "__init__", fake_probe_init), \
                    patch("b41_mipc_probe_resources.os", fake), \
                    patch("b41_mipc_probe_resources.seal_provider", return_value=88):
                with self.assertRaises(OSError) as caught:
                    ProbeXmlResources(STOCK, BIONIC, XML_ROOT)
                self.assertEqual(caught.exception.errno,
                                 errno.EBADMSG if bad_size or bad_copy else errno.EROFS)
                self.assertEqual([call.args[0] for call in fake.close.call_args_list],
                                 [77, 71, 72] if bad_size else [77, 71, 72, 88])

    def test_actual_independent_executable_pins(self):
        for relative, pin in (("probe", PROBE_SHA), ("vendor/lib64/libmnl.so", MNL_SHA)):
            data = (BIONIC / relative).read_bytes()
            self.assertEqual(data[:4], b"\x7fELF")
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin)

    def test_seal_failure_retains_first_with_both_cleanup_faults(self):
        base = Mock(close=Mock(side_effect=OSError(errno.EIO, "base close")))
        with patch("b41_mipc_probe_resources.LoaderResources", return_value=base), \
                patch("b41_mipc_probe_resources.os.open", return_value=77), \
                patch("b41_mipc_probe_resources.seal_provider", side_effect=OSError(errno.EBADMSG, "bad pin")), \
                patch("b41_mipc_probe_resources.os.close", side_effect=OSError(errno.EIO, "source close")):
            with self.assertRaises(OSError) as caught:
                ProbeResources(STOCK, BIONIC)
        self.assertEqual(caught.exception.errno, errno.EBADMSG)
        self.assertIn("source close", caught.exception.__notes__[0])
        self.assertIn("base close", caught.exception.__notes__[1])

    def test_adapter_retains_frozen_policy_and_deadline(self):
        source = Path(__file__).with_name("b41_mipc_sealed_isolate.c").read_text()
        self.assertIn('#include "mnl-isolate.c"', source)
        self.assertIn('if (filter())', source)
        self.assertNotIn('mount(root, root,', source)
        self.assertNotIn('mnl_run(', source)
        self.assertNotIn('mipc_init(', source)
        self.assertLess(source.index('return -ETIMEDOUT'), source.index('unshare(CLONE_NEWNET'))

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux sealing required in CI")
    def test_actual_twelve_sealed_descriptors_transfer(self):
        owned = ProbeResources(STOCK, BIONIC)
        descriptors = owned.move()
        try:
            self.assertEqual(len(descriptors), 12)
            for index, pin in ((10, PROBE_SHA), (11, MNL_SHA)):
                fd = descriptors[index]
                data = os.pread(fd, os.fstat(fd).st_size, 0)
                self.assertEqual(hashlib.sha256(data).hexdigest(), pin)
                self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o555 if index == 10 else 0o444)
                with self.assertRaises(OSError):
                    os.pwrite(fd, b"X", 0)
            with self.assertRaises(OSError):
                owned.move()
            owned.close()
            self.assertTrue(all(os.fstat(fd).st_size for fd in descriptors))
        finally:
            for fd in descriptors:
                os.close(fd)

    @unittest.skipUnless(hasattr(os, "memfd_create"), "Linux sealing required in CI")
    def test_actual_thirteen_xml_descriptors_transfer(self):
        owned = ProbeXmlResources(STOCK, BIONIC, XML_ROOT)
        descriptors = owned.move()
        try:
            self.assertEqual(len(descriptors), 13)
            fd = descriptors[12]
            data = os.pread(fd, XML_SIZE + 1, 0)
            self.assertEqual(len(data), XML_SIZE)
            self.assertEqual(hashlib.sha256(data).hexdigest(), XML_SHA)
            self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o444)
            seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
            self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals, seals)
            with self.assertRaises(OSError): os.pwrite(fd, b"X", 0)
            with self.assertRaises(OSError): owned.move()
            owned.close()
            self.assertTrue(all(os.fstat(fd).st_size for fd in descriptors))
        finally:
            for fd in descriptors: os.close(fd)


if __name__ == "__main__":
    unittest.main()
