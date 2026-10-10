"""Fixed immutable CI load-only executable, not a general executable admission."""
import os
import errno
from pathlib import Path
from b41_mipc_provider_resources import LoaderResources, _close_preserving
from b41_mipc_sealed_stage import seal_provider

# Existing independent CI37898372984 runtime artifact at2adc9cd94e7bcb6801b943990666fccf301ee1bd.
PROBE_SHA = "011a0dd90ab2043fd2eb8312024f000769d093b8e1b58e0e3540509122e7c214"
MNL_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
# Independent B4.1 vendor asset, not per-device NV/calibration or OEM signature.
# Kept consistent with the source-validated xml-policy-draft read profile.
XML_SHA = "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31"
XML_SIZE = 5087
XML_TARGET = "vendor/etc/MNL_Config.xml"


class ProbeResources:
    def __init__(self, stock_root, bionic_root):
        self.base = LoaderResources(stock_root, bionic_root)
        self.extra = []
        try:
            for path, pin, mode in ((Path(bionic_root) / "probe", PROBE_SHA, 0o555),
                                   (Path(bionic_root) / "vendor/lib64/libmnl.so", MNL_SHA, 0o444)):
                source = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    fd = seal_provider(source, pin)
                    self.extra.append(fd)
                    os.fchmod(fd, mode)
                except BaseException as error:
                    try:
                        os.close(source)
                    except BaseException as cleanup:
                        error.add_note(f"probe source cleanup also failed: {cleanup}")
                    raise
                else:
                    os.close(source)
        except BaseException as error:
            _close_preserving(self, error)
            raise

    def move(self):
        descriptors = self.base.move()
        descriptors.extend(self.extra)
        self.extra = []
        return descriptors

    def close(self):
        first = None
        try:
            self.base.close()
        except BaseException as error:
            first = error
        descriptors, self.extra = self.extra, []
        for fd in descriptors:
            try:
                os.close(fd)
            except BaseException as error:
                if first is None:
                    first = error
                else:
                    first.add_note(f"extra descriptor cleanup also failed: {error}")
        if first is not None:
            raise first


class ProbeXmlResources(ProbeResources):
    """Separate fixed 13-FD snapshot; never pass to the 12-FD load-only CLI.

    xml_artifact is the independently selected stock artifact root. Its fixed
    vendor/etc file is copied once, then the sealed copy's independent pin is
    checked before transfer. Neither the source path nor its stat authenticates
    bytes. No preferred data file, caller policy/default or readiness is added.
    """
    def __init__(self, stock_root, bionic_root, xml_artifact):
        super().__init__(stock_root, bionic_root)
        try:
            self._append_xml(xml_artifact)
        except BaseException as error:
            _close_preserving(self, error)
            raise

    def _append_xml(self, xml_artifact):
        """Append the fixed XML to an existing twelve-FD admitted snapshot."""
        if len(self.extra) != 2:
            raise ValueError("XML requires the original probe/libMNL pair")
        source = os.open(Path(xml_artifact) / XML_TARGET,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if os.fstat(source).st_size != XML_SIZE:
                raise OSError(errno.EBADMSG, "wrong independently pinned XML size")
            fd = seal_provider(source, XML_SHA)
            self.extra.append(fd)  # Existing close/move owns it immediately.
            if os.fstat(fd).st_size != XML_SIZE:
                raise OSError(errno.EBADMSG, "sealed XML size mismatch")
            os.fchmod(fd, 0o444)
        except BaseException as error:
            try:
                os.close(source)
            except BaseException as cleanup:
                error.add_note(f"XML source cleanup also failed: {cleanup}")
            raise
        else:
            os.close(source)
