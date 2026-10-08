#!/usr/bin/env python3
"""Exercise the actual APKBUILD link gate with fake tools, never compile C."""
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

PACKAGE = (Path(__file__).resolve().parents[2] /
           "pmaports/device/testing/linux-postmarketos-mediatek-mt6878")
MODULES = (
    "ccci_util/ccci_util_lib", "eccci/ccci_md_all", "eccci/ccci_auxadc",
    "eccci/hif/ccci_ccif", "eccci/hif/ccci_dpmaif", "eccci/hif/ccci_cldma",
    "eccci/fsm/ccci_fsm_scp", "ccmni/ccmni", "rps/rps_perf",
)


class LinkGate(unittest.TestCase):
    def run_gate(self, mode="ok"):
        recipe = (PACKAGE / "APKBUILD").read_text()
        function = re.search(r"^_build_modem_link\(\) \{.*?^\}", recipe,
                             re.M | re.S)[0]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            kernel, vendor = base / "kernel", base / "vendor"
            files = [kernel / "Module.symvers",
                     kernel / "include/config/kernel.release"]
            files += [vendor / path / "Module.symvers" for path in (
                "drivers/soc/mediatek", "drivers/rpmsg",
                "drivers/misc/mediatek/scp/rv")]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("6.18.0\n")
            if mode == "missing_exports":
                files[-1].unlink()
            (base / "modem-link.Kbuild").write_bytes(
                (PACKAGE / "modem-link.Kbuild").read_bytes())
            for name in MODULES:
                path = vendor / "drivers/misc/mediatek" / (name + ".ko")
                path.parent.mkdir(parents=True, exist_ok=True)
                if mode != "missing:" + name:
                    path.write_text("test fixture, not a module")
            # make/modinfo are shell functions to avoid any native compilation.
            script = f"""set -eu
srcdir={shlex.quote(str(base))}
builddir={shlex.quote(str(kernel))}
_devmods_dir={shlex.quote(str(vendor))}
_carch=arm64
JOBS=2
mode={shlex.quote(mode)}
die() {{ echo "$*" >&2; exit 1; }}
_vendor_kcflags() {{ :; }}
make() {{
    printf '%s\\n' "$@" > "$srcdir/make-args"
    test "$mode" != build_failure || return 42
    printf 'export fixture\\n' > "$srcdir/tetris-modem-link/Module.symvers"
}}
modinfo() {{
    case "$2" in
        name) name=${{3##*/}}; name=${{name%.ko}}
              test "$mode" != wrong_name || name=wrong
              printf '%s\\n' "$name" ;;
        vermagic) if test "$mode" = wrong_release; then echo 'other SMP';
                  else echo '6.18.0 SMP'; fi ;;
        *) return 99 ;;
    esac
}}
{function}
_build_modem_link
"""
            result = subprocess.run(["sh", "-c", script], text=True,
                                    capture_output=True)
            args_path = base / "make-args"
            args = args_path.read_text().splitlines() if args_path.exists() else []
            return result, args

    def test_joint_link(self):
        result, args = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        for item in ("modules", "LLVM=1", "ARCH=arm64", "KBUILD_MODPOST_WARN=",
                     "CONFIG_MTK_NET_CCMNI=m", "CONFIG_MTK_NET_RPS=m",
                     "CONFIG_MTK_ECCCI_DRIVER=m"):
            self.assertIn(item, args)
        symbols = next(arg for arg in args if arg.startswith("KBUILD_EXTRA_SYMBOLS="))
        self.assertEqual(symbols.count("Module.symvers"), 3)

    def test_missing_provider_prevents_make(self):
        result, args = self.run_gate("missing_exports")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, [])

    def test_failed_link_is_not_downgraded(self):
        result, _ = self.run_gate("build_failure")
        self.assertEqual(result.returncode, 42)

    def test_all_modules_required(self):
        for name in MODULES:
            with self.subTest(module=name):
                result, _ = self.run_gate("missing:" + name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Missing modem module", result.stderr)

    def test_module_identity_and_release(self):
        for mode in ("wrong_name", "wrong_release"):
            with self.subTest(mode=mode):
                result, _ = self.run_gate(mode)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
