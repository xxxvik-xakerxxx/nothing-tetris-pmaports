#!/usr/bin/env python3
"""Actual24-slot engine registration shape; retained global side effects offline."""
from pathlib import Path
import struct
import sys
import re
import shlex
import unittest


RECEIVER_CLOSURE = ("b41_agps_decode.c", "b41_agps_receiver.c",
                    "b41_agps_native.c", "b41_library_association.c")


def controller_compile_commands(source):
    for line in source.replace("\\\n", "").splitlines():
        tokens = shlex.split(line, comments=True)
        files = [token.rsplit("/", 1)[-1] for token in tokens if token.endswith(".c")]
        if {"b41_native_arguments.c", "b41_native_receiver_host.c"}.intersection(files):
            yield tokens, files


def receiver_compile_closure(source):
    commands = list(controller_compile_commands(source))
    for tokens, files in commands:
        for file in RECEIVER_CLOSURE:
            assert files.count(file) == 1, f"controller compile must link {file} exactly once"
        assert "-pthread" in tokens, "receiver owns a pthread worker"
        assert not any(token in ("-lmnl", "-D__BIONIC__", "-D__aarch64__") or
                       token.startswith(("-D__BIONIC__=", "-D__aarch64__=")) for token in tokens), \
            "fixtures must not load the vendor engine or synthesize its platform"
    return len(commands)


def admission_barriers(source):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    start = source.index("int b41_native_session_execute(")
    session = source[start:source.index("static int snapshot(", start)]
    barrier = "status = b41_native_worker_admission(worker);\n    if (status) return status;"
    after_barrier = "status = b41_native_worker_admission(worker);\n    if (status) { reason = status; goto quiesce_only; }"
    registration = session.index("result->registration_entered = 1;")
    registered = session.index("if (registration(&arguments->callbacks)) { reason = -EPROTO; goto quiesce_only; }")
    run = session.index("result->run_entered = 1;")
    first = session.find(barrier)
    second = session.find(after_barrier, first + len(barrier))
    assert 0 <= first < registration, "worker failure must reject before registration"
    assert registered < second < run, "worker failure must be rechecked before run"


def terminal_publication(source):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    run = source[source.index("static void *run("):source.index("int b41_frame_worker_start(")]
    tail = run[run.index("value = 1;"):]
    expected = """
        value = 1;
        ssize_t written = write(done, &value, sizeof(value));
        if (written != (ssize_t)sizeof(value)) fail(w, written < 0 ? -errno : -EIO);
        return NULL;
    }
    """
    assert re.sub(r'\s+', '', tail) == re.sub(r'\s+', '', expected), \
        "check publication once; only failure may access the owner afterward"


class WorkerAdmissionSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).with_name("b41_native_receiver_host.c").read_text()

    def test_registration_and_run_reject_dead_worker(self):
        admission_barriers(self.source)

    def test_completion_is_observed_without_consuming_quiescence_wake(self):
        start = self.source.index("int b41_native_worker_admission(")
        helper = self.source[start:self.source.index("int b41_native_session_execute(", start)]
        self.assertIn("atomic_load(&worker->failure)", helper)
        self.assertIn("atomic_load(&worker->stop_requested)", helper)
        self.assertIn("poll(&done, 1, 0)", helper)
        self.assertIn("return status ? status : -ESHUTDOWN", helper)
        self.assertNotIn("read(", helper)
        self.assertNotIn("close(", helper)
        self.assertNotIn("atomic_store(", helper)

    def test_worker_dispatch_failure_does_not_change_controller_state(self):
        source = Path(__file__).with_name("b41_frame_worker.c").read_text()
        run = source[source.index("static void *run("):source.index("int b41_frame_worker_start(")]
        self.assertIn("status = w->dispatch(w->ipc, &event)", run)
        self.assertIn("if (status) { fail(w, status); break; }", run)
        self.assertNotIn("w->state =", run)

    def test_frame_worker_terminal_publication_retains_original_error(self):
        source = Path(__file__).with_name("b41_frame_worker.c").read_text()
        terminal_publication(source)
        fail = source[source.index("static void fail("):source.index("static void *run(")]
        self.assertIn("atomic_compare_exchange_strong(&w->failure, &zero, error)", fail)
        quiesce = source[source.index("int b41_frame_worker_quiesce("):
                         source.index("int b41_frame_worker_release_unused(")]
        self.assertIn("if (worker_error) status = worker_error;", quiesce)
        self.assertIn("w->state = B41_WORKER_QUARANTINED;", quiesce)

    def test_terminal_publication_mutations_are_rejected(self):
        source = Path(__file__).with_name("b41_frame_worker.c").read_text()
        for original, replacement in (
            ("ssize_t written = write(done, &value, sizeof(value));", "(void)write(done, &value, sizeof(value));"),
            ("written != (ssize_t)sizeof(value)", "written < 0"),
            ("written < 0 ? -errno : -EIO", "-EIO"),
            ("    return NULL;", "    atomic_store(&w->failure, 0);\n    return NULL;"),
        ):
            with self.subTest(replacement=replacement):
                self.assertIn(original, source)
                with self.assertRaises(AssertionError):
                    terminal_publication(source.replace(original, replacement, 1))

    def test_publication_failure_ci_fixture_is_connected(self):
        runner = Path(__file__).with_name("run_native_receiver_host_ci.sh").read_text()
        self.assertIn("-D_FORTIFY_SOURCE=2", runner)
        self.assertIn("-O1", runner)
        self.assertIn("-Wl,--wrap=write", runner)
        fixture = Path(__file__).with_name("test_b41_native_receiver_host.c").read_text()
        self.assertIn("publication_failure_test(short_write, prior ? -EPIPE : 0)", fixture)
        self.assertIn("atomic_load(&publication_attempts) == 1", fixture)
        self.assertIn("poll(&done, 1, 0) == 0", fixture)
        self.assertIn("b41_frame_worker_release_unused(&worker) == -EPERM", fixture)

    def test_bionic_fixture_links_the_same_write_failure_wrapper(self):
        workflow = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
        source = workflow.read_text()
        body = source.split("for fixture in native_receiver_host native_arguments; do", 1)[1].split(
            "          done", 1)[0]
        self.assertIn('if test "$fixture" = native_receiver_host; then', body)
        self.assertIn("write_wrapper=()", body)
        self.assertIn("write_wrapper=(-Wl,--wrap=write)", body)
        self.assertIn('"${write_wrapper[@]}"', body)

    def test_missing_or_unchecked_barriers_are_rejected(self):
        barrier = "status = b41_native_worker_admission(worker);\n    if (status) return status;"
        after_barrier = "status = b41_native_worker_admission(worker);\n    if (status) { reason = status; goto quiesce_only; }"
        for index, barrier in enumerate((barrier, after_barrier)):
            start = self.source.index(barrier)
            for replacement in ("", "status = b41_native_worker_admission(worker);"):
                mutant = self.source[:start] + replacement + self.source[start + len(barrier):]
                with self.subTest(barrier=index, replacement=replacement):
                    with self.assertRaises(AssertionError):
                        admission_barriers(mutant)

    def test_existing_ci_runner_runs_source_checks_and_real_worker_fixture(self):
        runner = Path(__file__).with_name("run_native_receiver_host_ci.sh").read_text()
        self.assertLess(runner.index("--source-only"), runner.index('"${CC:-cc}"'))
        for source in ("b41_native_receiver_host.c", "b41_startup_adapter.c", "b41_agps_host.c",
                       "b41_navigation_output.c", "b41_frame_worker.c", "test_b41_native_receiver_host.c"):
            self.assertIn('"$here/' + source + '"', runner)

    def test_all_gnss_controller_compile_commands_link_receiver_closure(self):
        here = Path(__file__).parent
        discovered = set()
        for runner in here.rglob("*.sh"):
            with self.subTest(runner=str(runner.relative_to(here))):
                if receiver_compile_closure(runner.read_text()):
                    discovered.add(str(runner.relative_to(here)))
        self.assertTrue({
            "run_native_arguments_ci.sh", "run_native_receiver_host_ci.sh",
            "run_mipc_sealed_launch_ci.sh", "run_mipc_loader_resources_ci.sh",
            "run_mipc_supervised_child_ci.sh", "run_sealed_probe_parent_ci.sh",
            "lna-start-contract/run_ci.sh", "native-agps-receiver/run_controller_ci.sh",
        }.issubset(discovered))

    def test_missing_duplicate_or_split_compile_closures_are_rejected(self):
        runner = Path(__file__).with_name("run_mipc_loader_resources_ci.sh").read_text()
        self.assertEqual(receiver_compile_closure(runner), 1)
        for file in RECEIVER_CLOSURE:
            token = '"$here/' + ("native-agps-receiver/" if file.startswith("b41_agps_") else "") + file + '"'
            self.assertIn(token, runner)
            for replacement in ("", token + " " + token, "\n" + token):
                with self.subTest(file=file, replacement=replacement):
                    with self.assertRaises(AssertionError):
                        receiver_compile_closure(runner.replace(token, replacement, 1))
        for replacement in ("", "-pthread -lmnl", "-pthread -D__BIONIC__=1"):
            with self.subTest(flags=replacement):
                with self.assertRaises(AssertionError):
                    receiver_compile_closure(runner.replace("-pthread", replacement, 1))

    def test_controller_fixtures_do_not_enter_engine_or_fake_native_platform(self):
        here = Path(__file__).parent
        for file in ("test_b41_native_receiver_host.c", "test_b41_native_arguments.c"):
            fixture = (here / file).read_text()
            fixture = re.sub(r'/\*.*?\*/|//[^\n]*', '', fixture, flags=re.S)
            self.assertNotRegex(fixture, r'\b(?:b41_native_session_execute|b41_native_stop_call|dlopen)\s*\(')
            for forbidden in ("__wrap_b41_native_session_execute", "__wrap_b41_native_stop_call"):
                self.assertNotIn(forbidden, fixture)
        arguments = (here / "test_b41_native_arguments.c").read_text()
        self.assertIn("b41_native_arguments_execute(owner, NULL, NULL, NULL) == -EINVAL", arguments)
        self.assertIn("owner->first_error = -ESTALE;", arguments)
        self.assertIn("b41_native_arguments_execute(owner, NULL, NULL, NULL) == -ESTALE", arguments)
        runner = (here / "native-agps-receiver/run_controller_ci.sh").read_text()
        self.assertNotIn("timeout", runner)
        self.assertNotRegex(runner, re.compile(r'^\s*"\$output/b41-.*controller-test"\s*$', re.M))

def verify(path):
    from test_b41_startup import Machine, LIB_SHA, DATA, STOP
    for missing in [None] + list(range(10)):
        m=Machine(path,LIB_SHA,[(0x52f9d0,0x52fbb0)])
        slots=[STOP+0x100+8*i if i!=missing else 0 for i in range(10)]+[0]*14
        m.u.mem_write(DATA,struct.pack("<24Q",*slots))
        m.run(0x52f9d0,args=(DATA,))
        required=missing is not None and bool(0x3fb & (1<<missing))
        assert m.args()[0]==(0xffffffff if required else 0)
        for slot,got in ((1,0x6e6800),(3,0x6e6d30),(4,0x6e6d28)):
            assert struct.unpack("<Q",m.u.mem_read(m.global_at(got),8))[0]==slots[slot]
    print("PASS: actual24-slot table with all14 optional NULL; mandatory0x3fb; failed calls retain globals")

if __name__ == "__main__":
    if sys.argv[1:] == ["--source-only"]:
        unittest.main(argv=[sys.argv[0]])
    elif len(sys.argv) == 2:
        verify(Path(sys.argv[1]))
    else:
        raise SystemExit("usage: test_b41_engine_registration_shape.py --source-only | libmnl.so")
