#!/usr/bin/env python3
"""Production reverse-owner integration and pinned run boundary, static only."""
from pathlib import Path
import re
import sys
import unittest

from private_evidence import HERE, load


def code(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def session(text):
    text = code(text)
    start = text.index("int b41_native_session_execute(")
    return text[start:text.index("static int snapshot(", start)]


def lifecycle(text):
    body = session(text)
    gate = body.index("if (arguments->missing_contracts) return -EOPNOTSUPP;")
    run = body.index("result->run_status = run(arguments->first, arguments->second);")
    failed_run = body.index("if (result->run_status != 18) { reason = -EPROTO; goto quiesce_only; }")
    activate = body.index("result->agps_activation_status = b41_agps_receiver_activate(agps);")
    observe = body.index("for (;;) {", activate)
    stop = body.index("stop_session:")
    quiesce = body.index("result->agps_quiesce_status = b41_agps_receiver_quiesce(agps, worker_deadline);", stop)
    ack = body.index("if (agps->state != B41_AGPS_RX_QUIESCED)", quiesce)
    capture = body.index("result->native_stop_status = b41_native_stop_capture(stop, image);")
    native_stop = body.index("result->native_stop_status = b41_native_stop_call(stop, &result->joined_threads);")
    assert gate < run < failed_run < activate < observe < stop < quiesce < ack < capture < native_stop
    assert "goto stop_session;" in body[activate:observe]
    refusal = body[ack:capture]
    assert "return reason ? reason : -EBUSY;" in refusal
    assert "result->native_stop_status = -ECANCELED;" in refusal
    assert "result->worker_stop_status = -EBUSY;" in refusal
    assert "if (!reason) reason = result->agps_quiesce_status;" in body[quiesce:ack]
    assert "if (reason) return reason;" in body[native_stop:]
    failed = body[body.index("quiesce_only:"):]
    assert "b41_agps_receiver_quiesce(agps, worker_deadline)" in failed
    assert "return reason ? reason : result->agps_quiesce_status;" in failed
    assert "b41_native_stop_" not in failed


class ControllerSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld, cls.lib = load(MNLD, LIB)
        cls.host = (HERE.parent / "b41_native_receiver_host.c").read_text()
        cls.producer = (HERE.parent / "b41_native_arguments.c").read_text()
        cls.receiver = (HERE / "b41_agps_receiver.c").read_text()

    def test_exact_native_run_boundary(self):
        for address, expected in {
            0x63c34: ("adr", "x0, #0xde520"),
            0x63c3c: ("adr", "x1, #0xde590"),
            0x63c40: ("bl", "#0x859b0"),
            0x63c44: ("mov", "w21, w0"),
            0x63c7c: ("cmp", "w21, #0x12"),
            0x63c88: ("b.ne", "#0x63ccc"),
        }.items():
            self.assertEqual(self.mnld.instructions(address, 4)[address], expected)
        self.assertEqual(self.mnld.imported_symbol(0x86e08), (1026, b"mtk_gps_mnl_run"))
        self.assertEqual(self.lib.instructions(0x52e2bc, 4)[0x52e2bc], ("b", "#0x52b638"))
        self.assertIn("image->base + 0x52e2bcu", session(self.host))

    def test_existing_production_owner_prepares_and_passes_receiver(self):
        header = (HERE.parent / "b41_native_arguments.h").read_text()
        self.assertIn("struct b41_agps_receiver agps;", header)
        prepare = code(self.producer).split("int b41_native_arguments_prepare(", 1)[1].split(
            "int b41_native_arguments_execute(", 1)[0]
        self.assertLess(prepare.index("o->entered = 1;"),
                        prepare.index("b41_agps_receiver_open(&o->agps, peer_pid, peer_uid)"))
        self.assertLess(prepare.index("b41_agps_receiver_prepare(&o->agps, elf, elf_size, view)"),
                        prepare.index("b41_frame_worker_start("))
        self.assertIn("if (peer_pid <= 0) return -EINVAL;", prepare)
        self.assertIn("if (status < 0) goto fail;", prepare)
        for field in ("base", "extent", "xml_global", "chip_global"):
            self.assertIn(f"o->agps.image.{field} != image.{field}", prepare)
            self.assertIn(f"agps->image.{field} != image->{field}", session(self.host))
        self.assertNotIn("b41_agps_receiver_activate", prepare)
        execute = code(self.producer).split("int b41_native_arguments_execute(", 1)[1]
        self.assertIn("&o->worker, &o->stop, &o->agps, run, worker, result", execute)
        self.assertIn("if (o->executed) return -EALREADY;", execute)
        self.assertIn("o->executed = 1;", execute)
        self.assertLess(execute.index("o->agps.controller_pid != getpid()"),
                        execute.index("o->executed = 1;"))
        self.assertIn("!pthread_equal(o->agps.controller, pthread_self())", execute)
        self.assertIn("if (!result->agps_quiesce_entered &&", execute)
        self.assertIn("b41_agps_receiver_quiesce(&o->agps, worker)", execute)
        self.assertIn("if (!status) status = result->agps_quiesce_status;", execute)
        self.assertIn("if (status && !o->first_error) o->first_error = status;", execute)

    def test_post_run_activation_and_pre_stop_completion(self):
        lifecycle(self.host)

    def test_lifetime_mutations_are_refused(self):
        for before, after in (
            ("result->run_status != 18", "result->run_status == 18"),
            ("agps->state != B41_AGPS_RX_QUIESCED", "!result->agps_quiesce_status"),
            ("if (!reason) reason = result->agps_quiesce_status;", "reason = result->agps_quiesce_status;"),
            ("return reason ? reason : -EBUSY;", "reason = 0;"),
            ("goto quiesce_only;", "return reason;"),
            ("if (reason) return reason;", "reason = 0;"),
        ):
            with self.subTest(mutation=after):
                self.assertIn(before, self.host)
                with self.assertRaises((AssertionError, ValueError)):
                    lifecycle(self.host.replace(before, after))

    def test_receiver_completion_and_failure_in_production_poll_loop(self):
        body = session(self.host)
        self.assertIn("pollset[2] = (struct pollfd){agps->fd[2], POLLIN, 0};", body)
        loop = body[body.index("for (;;) {"):body.index("stop_session:")]
        self.assertIn("if (!reason) reason = b41_agps_receiver_observe(agps);", loop)
        self.assertIn("poll(pollset, 3, ms)", loop)
        self.assertIn("if (pollset[2].revents)", loop)
        helper = code(self.receiver).split("int b41_agps_receiver_observe(", 1)[1].split(
            "int b41_agps_receiver_open(", 1)[0]
        for expected in ("if (!controller(o)) return -EPERM;", "atomic_load(&o->first_error)",
                         "same_fd(o, i)", "poll(&done, 1, 0)", "atomic_load(&o->stop)"):
            self.assertIn(expected, helper)
        for forbidden in ("read(", "close(", "atomic_store(", "b41_agps_native_"):
            self.assertNotIn(forbidden, helper)
        self.assertIn("o->controller_pid == getpid()", self.receiver)
        self.assertIn("pthread_equal(o->controller, pthread_self())", self.receiver)
        for method in ("prepare", "activate", "quiesce", "close"):
            method_body = code(self.receiver).split(f"int b41_agps_receiver_{method}(", 1)[1].split(
                "\n}\n", 1)[0]
            self.assertIn("if (!controller(o)) return -EPERM;", method_body)
        activate = code(self.receiver).split("int b41_agps_receiver_activate(", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(activate.index("if (!controller(o)) return -EPERM;"),
                        activate.index("status = b41_agps_receiver_observe(o);"))

    def test_peer_is_supplied_by_supervisor_without_fallback_identity(self):
        prepare = code(self.producer).split("int b41_native_arguments_prepare(", 1)[1].split(
            "int b41_native_arguments_execute(", 1)[0]
        self.assertIn("pid_t peer_pid, uid_t peer_uid", prepare)
        self.assertIn("b41_agps_receiver_open(&o->agps, peer_pid, peer_uid)", prepare)
        self.assertNotRegex(prepare, r'\b(?:getpid|getppid|getuid|geteuid)\s*\(')
        opened = code(self.receiver).split("int b41_agps_receiver_open(", 1)[1].split(
            "static int receive_one(", 1)[0]
        self.assertEqual(re.findall(r'o->peer_pid\s*=\s*([^;]+);', opened), ["peer"])
        self.assertEqual(re.findall(r'o->peer_uid\s*=\s*([^;]+);', opened), ["uid"])
        self.assertIn("peer.pid != o->peer_pid || peer.uid != o->peer_uid", self.receiver)

    def test_no_gate_or_native_state_fabrication(self):
        self.assertIn("missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;", self.producer)
        self.assertIn("if (arguments->missing_contracts) return -EOPNOTSUPP;", session(self.host))
        for forbidden in ("agps_receiver_close(", "dlclose(", "pthread_cancel(", "pthread_kill("):
            self.assertNotIn(forbidden, code(self.producer) + session(self.host))
        self.assertNotRegex(code(self.producer) + session(self.host), r'\bfree\s*\(')
        self.assertNotRegex(session(self.host), r"run_status\s*=\s*18\s*;")
        self.assertNotRegex(session(self.host), r"missing_contracts\s*(?:=|&=)")

    def test_ci_closure_links_actual_production_and_retains_write_wrapper(self):
        runner = (HERE / "run_controller_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("--bionic-compile", runner)
        self.assertIn("for fixture in native_receiver_host native_arguments; do", runner)
        for file in ("b41_native_arguments.c", "b41_native_receiver_host.c", "b41_library_association.c",
                     "b41_slot6_service.c", "b41_engine_arguments.c", "b41_gpsdl_identity.c",
                     "b41_startup_adapter.c", "b41_agps_host.c", "b41_frame_worker.c",
                     "b41_navigation_output.c", "b41_agps_decode.c", "b41_agps_receiver.c", "b41_agps_native.c"):
            self.assertIn(file, runner)
        self.assertIn("-Wl,--wrap=write", runner)
        self.assertIn('"$@" -o "$output/b41-${fixture}-controller-test"', runner)
        self.assertNotIn("timeout", runner)
        fixture = (HERE / "test_receiver.c").read_text()
        self.assertIn("observer_ownership, observer_failure", fixture)
        self.assertIn("b41_agps_receiver_observe(&owner) == -EPIPE", fixture)
        self.assertIn("b41_agps_receiver_observe(&owner) == -EPERM", fixture)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_controller.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
