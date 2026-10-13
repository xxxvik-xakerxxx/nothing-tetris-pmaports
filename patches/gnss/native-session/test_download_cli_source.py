#!/usr/bin/env python3
"""Retained CLI source and orchestration checks; no C build or device access."""
from pathlib import Path
import os
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLI = ROOT / "patches/gnss-navigation-audit/dsp-download/live-inputs/selectors.c"


class RetainedCLI(unittest.TestCase):
    def test_same_descriptor_and_deadline_precede_download(self):
        source = CLI.read_text().split("int main(", 1)[1]
        self.assertEqual(source.count('open("/dev/gpsdl0"'), 1)
        self.assertLess(source.index("retain_fd = 1;"), source.index("b41_session_attach("))
        self.assertLess(source.index("b41_session_attach(&retained, gps_fd, deadline)"),
                        source.index("b41_native_l1_download_linux_begin(&owner"))
        self.assertIn("retained.latest.dsp_state != 1u && retained.latest.dsp_state != 2u", source)
        self.assertEqual(source.count("deadline ="), 1)

    def test_real_work_stop_and_terminal_hold_precede_close(self):
        source = CLI.read_text()
        main = source.split("int main(", 1)[1]
        self.assertLess(main.index("owner.stage != B41_DOWNLOAD_ACKS_COMPLETE"),
                        main.index("b41_session_wait_step(&retained)"))
        self.assertLess(main.index("b41_session_wait_step(&retained)"),
                        main.index("b41_session_stop_begin(&retained)"))
        self.assertLess(main.index("b41_session_stop_step(&retained)"),
                        main.index("retain_for_cold_recovery("))
        self.assertLess(main.index("retain_for_cold_recovery("), main.index("close(gps_fd)"))
        self.assertIn("status || retained.stage != B41_SESSION_STOPPED", main)
        hold = source.split("static void retain_for_cold_recovery(", 1)[1].split("#endif", 1)[0]
        self.assertIn("alarm(0);", hold)
        self.assertIn("for (;;) pause();", hold)
        for operation in ("close(", "ioctl(", "write(", "open(", "exit(", "return "):
            self.assertNotIn(operation, hold)

    def test_deadlines_and_signals_never_restart_download(self):
        source = CLI.read_text().split("int main(", 1)[1]
        self.assertEqual(source.count("b41_native_l1_download_linux_begin("), 1)
        self.assertIn("sigaction(SIGHUP, &action", source)
        self.assertIn("sigaction(SIGPIPE, &action", source)
        self.assertIn("#else\n    action.sa_handler = SIG_DFL;\n#endif", source)
        self.assertIn("interrupted ? -EINTR : -ETIMEDOUT", source)
        self.assertNotIn("scalar_query(gps_fd, 12", source)
        self.assertNotIn("ioctl(gps_fd, 12", source)

    def test_native_fixture_covers_close_and_live_hold_boundaries(self):
        source = (HERE / "test_download_cli.c").read_text()
        for state in ("ATTACH_FAIL", "INHERITED_WORK", "METADATA_FAIL", "DOWNLOAD_FAIL",
                      "WAIT_FAIL", "STOP_FAIL", "INTERRUPTED"):
            self.assertIn(state, source)
        self.assertIn("scenario == SUCCESS && stops == 3", source)
        self.assertIn("scenario != SUCCESS && !gps_closes && opens == 3", source)
        runner = (HERE / "run_download_ci.sh").read_text()
        self.assertIn("-Dmain=b41_retained_main", runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertIn('"$here/session.c"', runner)
        self.assertIn("-DB41_NATIVE_L1_RETAINED_SESSION", runner)

    def test_compilation_refuses_locally_without_creating_output(self):
        result = subprocess.run(["sh", str(HERE / "run_download_ci.sh"), "no-compiler", "/not-created"],
                                env={**os.environ, "CI": "false", "GITHUB_ACTIONS": "false"},
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("GitHub CI-only", result.stderr)

    def test_ci_requires_real_session_native_fixtures_before_artifact(self):
        workflow = (ROOT / ".github/workflows/gnss-xml-adc.yml").read_text()
        self.assertIn("python3 -B patches/gnss/native-session/run.py --ci-native", workflow)
        self.assertIn("sh patches/gnss/native-session/run_download_ci.sh", workflow)
        self.assertIn("requires=matching-1010-kernel-and-v051-suppliers", workflow)


if __name__ == "__main__":
    unittest.main()
