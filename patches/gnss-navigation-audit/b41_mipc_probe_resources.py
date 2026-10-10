"""Fixed immutable CI load-only executable, not a general executable admission."""
import os
from pathlib import Path
from b41_mipc_provider_resources import LoaderResources, _close_preserving
from b41_mipc_sealed_stage import seal_provider

# Existing independent CI37898372984 runtime artifact at2adc9cd94e7bcb6801b943990666fccf301ee1bd.
PROBE_SHA = "011a0dd90ab2043fd2eb8312024f000769d093b8e1b58e0e3540509122e7c214"
MNL_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"


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
