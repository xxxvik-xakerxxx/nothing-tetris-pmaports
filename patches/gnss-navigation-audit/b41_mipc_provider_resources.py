"""Pinned genuine B4.1 provider closure and sealed loader-root descriptor order."""
import errno
import os
from pathlib import Path

from b41_mipc_init_resources import acquire
from b41_mipc_sealed_stage import SealedStage

LIBLOG_SHA = "dce4ece329f925cdc0b181b3e5f11b54d92a24e49b1b90b121a4e0f960df84fd"
LIBLOG_SIZE = 102352
# Exact C mount-table order. ld-android.so is supplied by linker64, not a stub.
LAYOUT = (
    ("ld-android.so", "apex/com.android.runtime/bin/linker64"),
    ("libc.so", "apex/com.android.runtime/lib64/bionic/libc.so"),
    ("libm.so", "apex/com.android.runtime/lib64/bionic/libm.so"),
    ("libdl.so", "apex/com.android.runtime/lib64/bionic/libdl.so"),
    ("libc++.so", "system/lib64/libc++.so"),
    ("liblog.so", "system/lib64/liblog.so"),
    ("libmipc.so", "vendor/lib64/libmipc.so"),
    ("libmtkrillog.so", "vendor/lib64/libmtkrillog.so"),
    ("libtrm.so", "vendor/lib64/libtrm.so"),
    ("libmtkproperty.so", "vendor/lib64/libmtkproperty.so"),
)


def _close_preserving(owner, original):
    try:
        owner.close()
    except BaseException as cleanup:
        original.add_note(f"resource cleanup also failed: {type(cleanup).__name__}: {cleanup}")


def acquire_providers(stock_root, bionic_root):
    """No arbitrary liblog path/pin, NDK search or service-readiness override."""
    stock_root, bionic_root = Path(stock_root), Path(bionic_root)
    resources = acquire(stock_root / "vendor/lib64", bionic_root,
                        ((stock_root / "system/lib64/liblog.so", LIBLOG_SHA),))
    try:
        if set(resources.images) != {name for name, _ in LAYOUT}:
            raise OSError(errno.ENODATA, "unexpected provider closure")
        fd = resources.descriptors["liblog.so"]
        if os.fstat(fd).st_size != LIBLOG_SIZE:
            raise OSError(errno.EBADMSG, "wrong pinned liblog size")
        image = resources.images["liblog.so"]
        for name in ("__android_log_buf_write", "__android_log_assert"):
            exports = [s for s in image["symbols"] if s["name"] == name and not s["undefined"]
                       and s["type"] == "STT_FUNC" and not s["hidden_version"]
                       and s["version"] and s["version"]["name"] == "LIBLOG"]
            if len(exports) != 1:
                raise OSError(errno.ELIBBAD, "required real LIBLOG export absent", name)
        return resources
    except BaseException as error:
        _close_preserving(resources, error)
        raise


class LoaderResources:
    """Single owner until move; no execution, namespace, property or modem calls."""
    def __init__(self, stock_root, bionic_root):
        self.stage = None
        resources = None
        try:
            resources = acquire_providers(stock_root, bionic_root)
            self.report = resources.report
            self.stage = SealedStage(resources)
            resources.close()
            resources = None
            for name, _ in LAYOUT:
                # File modes only; byte/hash immutability is supplied by seals.
                os.fchmod(self.stage.descriptors[name], 0o555 if name == "ld-android.so" else 0o444)
        except BaseException as error:
            if resources is not None:
                _close_preserving(resources, error)
            if self.stage is not None:
                _close_preserving(self.stage, error)
            raise

    def move(self):
        descriptors = self.stage.move()
        return [descriptors[name] for name, _ in LAYOUT]

    def close(self):
        self.stage.close()

    def __enter__(self):
        return self

    def __exit__(self, _kind, error, _traceback):
        if error is not None:
            _close_preserving(self.stage, error)
        else:
            self.close()
