#!/usr/bin/env python3
"""B4.1 quiet startup and native configuration delivery, no CPU execution."""
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent


def body(source, start, end):
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    return source.split(start, 1)[1].split(end, 1)[0]


class SourceTests(unittest.TestCase):
    def test_fixed_binary_configuration_copies_before_queue_publication(self):
        header = (HERE / "b41_agps_host.h").read_text()
        self.assertIn("#define B41_AGPS_CONFIGURATION_SIZE 0x29cu", header)
        self.assertIn("uint8_t bytes[B41_AGPS_CONFIGURATION_SIZE]", header)
        source = (HERE / "b41_slot6_service.c").read_text()
        callback = body(source, "static int32_t callback(", "int b41_slot6_service_bind(")
        config = callback.split("else if (selector == 7)", 1)[1].split("else return fail", 1)[0]
        self.assertIn("if (!(parameter & 0xffffu)) return 0;", config)
        self.assertIn("(parameter & 0xffffu) != B41_AGPS_CONFIGURATION_SIZE", config)
        self.assertIn("b41_agps_configuration_packet(pointer, packet, sizeof(packet), &written)", config)
        self.assertLess(callback.index("b41_agps_configuration_packet("), callback.index("memcpy(event->bytes, packet, written)"))
        self.assertNotRegex(callback, r'\b(?:send|sendto|b41_agps_owner_send_configuration)\s*\(')
        self.assertNotIn("event->pointer", callback)

    def test_exact_extent_and_original_failure_survive_real_send(self):
        host = (HERE / "b41_agps_host.c").read_text()
        producer = body(host, "int b41_agps_configuration_packet(", "int b41_agps_owner_init(")
        for expected in ("if (!config || !output || !written) return -EINVAL;",
                         "if (capacity < size) return -ENOSPC;", "word(out + 4, 160);",
                         "word(out + 8, sizeof(*config));", "memcpy(out + 12, config, sizeof(*config));"):
            self.assertIn(expected, producer)
        self.assertNotIn("strlen", producer)
        self.assertNotIn("memchr", producer)
        send = body(host, "static int send_packet(", "int b41_agps_owner_send_data(")
        self.assertLess(send.index("if (owner->first_error)"), send.index("send(owner->fd"))
        self.assertIn("MSG_DONTWAIT | MSG_NOSIGNAL", send)
        self.assertIn("owner->first_error = status;", send)
        dispatch = body((HERE / "b41_slot6_service.c").read_text(),
                        "int b41_slot6_service_dispatch(", "\n}\n")
        self.assertIn("event->length != 12u + B41_AGPS_CONFIGURATION_SIZE", dispatch)
        self.assertIn("word(event->bytes + 8) != B41_AGPS_CONFIGURATION_SIZE", dispatch)
        self.assertIn("b41_agps_owner_send_configuration(ipc", dispatch)

    def test_hook_is_used_by_native_production_owner_without_gate_exemption(self):
        source = (HERE / "b41_native_arguments.c").read_text()
        self.assertLess(source.index("b41_slot6_service_bind(&o->adapter, &callbacks)"),
                        source.index("b41_engine_arguments_build("))
        self.assertLess(source.index("o->worker.dispatch = b41_slot6_service_dispatch;"),
                        source.index("b41_frame_worker_start("))
        self.assertIn("missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;", source)
        host = (HERE / "b41_native_receiver_host.c").read_text()
        self.assertIn("if (arguments->missing_contracts) return -EOPNOTSUPP;", host)
        for forbidden in ("missing_contracts", "property_set", "dlopen(", "pthread_cancel", "pthread_kill"):
            self.assertNotIn(forbidden, (HERE / "b41_slot6_service.c").read_text())

    def test_existing_ci_fixtures_cover_binary_copy_extent_and_real_worker(self):
        for runner_name in ("run_agps_host_ci.sh", "run_slot6_service_ci.sh"):
            runner = (HERE / runner_name).read_text()
            self.assertIn("--source-only", runner)
            self.assertIn('"${CI:-}" != true', runner)
            self.assertIn("-fsanitize=address,undefined", runner)
        fixture = (HERE / "test_b41_slot6_service.c").read_text()
        for expected in ("scenario < 11", "saved = config;", "memset(&config, 0, sizeof(config));",
                         "0xffff0000u | sizeof(config)", "b41_frame_worker_quiesce(&worker, &deadline)",
                         "--bad.length", "++bad.length", "ipc.first_error == first"):
            self.assertIn(expected, fixture)
        self.assertNotRegex(fixture, r'\b(?:b41_native_session_execute|dlopen|b41_native_arguments_execute)\s*\(')
        packet = (HERE / "test_b41_agps_host.c").read_text()
        self.assertIn("capacity < sizeof(packet)", packet)
        self.assertIn("160,0,0,0,0x9c,2,0,0", packet)


class PinnedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, image, expectations):
        for address, expected in expectations.items():
            self.assertEqual(image.instructions(address, 4)[address], expected, hex(address))

    def test_normal_host_run18_does_not_skip_agent_for_quiet_logging(self):
        self.check(self.mnld, {0x63544: ("cmp", "w8, #1"),
                              0x63c40: ("bl", "#0x859b0"),
                              0x63c7c: ("cmp", "w21, #0x12")})
        self.check(self.lib, {
            0x52b6a4: ("ldr", "w8, [x22, #0x68]"),
            0x52bfd8: ("tbnz", "w8, #4, #0x52c004"),
            0x52c05c: ("tbnz", "w1, #4, #0x52c090"),
            0x52c420: ("ldr", "w8, [x22, #0x68]"),
            0x52c428: ("b.ne", "#0x52c43c"),
            0x52c43c: ("mov", "w0, #4"),
            0x52c440: ("bl", "#0x52a424"),
            0x52c444: ("cbz", "w0, #0x52c458"),
            0x52c4d8: ("mov", "w19, #0x12"),
            0x52a4b8: ("bl", "#0x52b500"),
            0x52a4c8: ("adrp", "x2, #0x52d000"),
            0x52a4cc: ("add", "x2, x2, #0x870"),
            0x52d904: ("ldrb", "w8, [x8, #4]"),
            0x52d908: ("and", "w0, w8, #1"),
            0x52d90c: ("bl", "#0x6e53b0"),
        })
        self.assertEqual(0x52a478 + self.lib.read(0x4c4a19 + 4, 1)[0] * 4, 0x52a4b8)
        self.assertEqual(self.lib.imported_symbol(0x6e90d0), (1026, b"mtk_agps_agent_init"))
        # The actual argument is diagnostic bit0; no bypass surrounds this call.
        self.assertEqual(list(self.lib.instructions(0x52d900, 16).values()), [
            ("ldr", "x8, [x8, #0x9d0]"), ("ldrb", "w8, [x8, #4]"),
            ("and", "w0, w8, #1"), ("bl", "#0x6e53b0")])

    def test_constellation_pairs_are_distinct_from_service_configuration(self):
        self.check(self.lib, {0x52e91c: ("mov", "w10, #0x21"),
                             0x52e924: ("bics", "wzr, w10, w9"),
                             0x52e92c: ("cset", "w10, eq"),
                             0x53ef4c: ("ldr", "w8, [x8]"),
                             0x53ef88: ("tbnz", "w8, #1, #0x53efa8"),
                             0x53ef8c: ("mov", "w9, #1"),
                             0x53ef9c: ("str", "w9, [x0, #4]")})
        # A separate request-configuration word controls these service fields.
        # This is a counterexample to equating the satellite mask with readiness,
        # not a claim to have proven every firmware/runtime path reachable.
        self.assertEqual(self.lib.read(0x6e6d20, 8), (0x88b5e8).to_bytes(8, "little"))

    def test_second_policy_has_consumers_independent_of_constellation_mask(self):
        self.check(self.lib, {
            0x52b69c: ("mov", "w2, #0x444"),
            0x52b6a0: ("bl", "#0x6e48e0"),
            0x52b6c0: ("ldr", "w8, [x19, #0xc8]"),
            0x52c388: ("ldrb", "w8, [x19, #0x18]"),
            0x52c38c: ("cmp", "w8, #1"),
            0x52c390: ("b.ne", "#0x52c420"),
        })
        second = (HERE / "b41_second_config.c").read_text()
        self.assertIn("result.provenance[i] == B41_SECOND_UNKNOWN", second)
        self.assertIn("result.mpe_schema_missing = 1;", second)
        self.assertIn("memcpy(result.bytes + 0x70, inputs->mpe_state, 68)", second)

    def test_native_snapshot_and_exact_mnld_type160_wire_producer(self):
        self.check(self.lib, {
            0x6a6ecc: ("cbz", "x0, #0x6a7168"),
            0x6a6eec: ("cbnz", "w0, #0x6a7168"),
            0x6a70e0: ("add", "x0, sp, #0x60"),
            0x6a70e4: ("bl", "#0x53ef3c"),
            0x6a70ec: ("ldr", "x8, [x8, #0x850]"),
            0x6a70f4: ("add", "x2, sp, #0x60"),
            0x6a70f8: ("mov", "w0, #7"),
            0x6a70fc: ("mov", "w1, #0x29c"),
            0x6a7100: ("blr", "x8"),
        })
        self.check(self.mnld, {
            0x5fae4: ("b.eq", "#0x5fc80"),
            0x5fc80: ("tst", "w21, #0xffff"),
            0x5fc84: ("b.eq", "#0x5fe80"),
            0x5fc88: ("and", "w1, w21, #0xffff"),
            0x5fc8c: ("mov", "x0, x19"),
            0x5fc90: ("bl", "#0x398d0"),
            0x39914: ("mov", "w2, #1"),
            0x39928: ("mov", "w2, #0xa0"),
            0x3993c: ("mov", "w3, w19"),
            0x39940: ("bl", "#0x35730"),
            0x3994c: ("bl", "#0x380a0"),
            0x35748: ("strb", "w3, [x0, x8]"),
            0x35758: ("strb", "w9, [x0, x8]"),
            0x3576c: ("strb", "w9, [x0, x8]"),
            0x35780: ("strb", "w9, [x0, x8]"),
            0x357ac: ("bl", "#0x85240"),
        })


if __name__ == "__main__":
    if sys.argv[1:] == ["--source-only"]:
        unittest.main(argv=[sys.argv[0]], defaultTest="SourceTests")
    elif len(sys.argv) == 3:
        MNLD, LIB = map(Path, sys.argv[1:])
        unittest.main(argv=[sys.argv[0]])
    else:
        raise SystemExit("usage: test_b41_agps_configuration_source.py --source-only | PINNED_MNLD PINNED_LIBMNL")
