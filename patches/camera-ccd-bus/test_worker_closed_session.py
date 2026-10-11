#!/usr/bin/env python3
"""Source gates for clean CCD DESTROY -> retirement; no C or device execution."""
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent


class ClosedSessionSourceTests(unittest.TestCase):
    def test_closed_gate_is_after_query_before_receive(self):
        source = (HERE / "ccd-worker-owner.c").read_text()
        step = source.split("int mt6878_ccd_worker_owner_step(", 1)[1]
        query = step.index("MT6878_CCD_RETIRE_QUERY")
        error = step.index("if (owner->first_error)", query)
        closed = step.index("if (session->closed && !session->first_error)", error)
        receive = step.index("mt6878_ccd_worker_receive_once(", closed)
        branch = step[closed:receive]
        self.assertIn("ret = -ESHUTDOWN;", branch)
        self.assertIn("goto out;", branch)
        self.assertNotIn("goto fail;", branch)
        self.assertNotIn("MT6878_CCD_RETIRE_ACK", branch)
        self.assertNotIn("composition_failed =", branch)

    def test_retirement_still_requires_ticket_and_clean_composition(self):
        source = (HERE / "ccd-worker-owner.c").read_text()
        step = source.split("int mt6878_ccd_worker_owner_step(", 1)[1]
        ticket = step.index("if (!ticket.token")
        failure = step.index("if (owner->composition_failed || session->first_error)", ticket)
        closed = step.index("session->closed = 1;", failure)
        ack = step.index("MT6878_CCD_RETIRE_ACK", closed)
        retired = step.index("owner->retired = 1;", ack)
        self.assertLess(ticket, failure)
        self.assertLess(failure, closed)
        self.assertLess(closed, ack)
        self.assertLess(ack, retired)

    def test_native_regressions_use_real_dispatch_and_preserve_failed_end(self):
        mapped = (HERE / "mapped-worker-test.c").read_text()
        flush = mapped.index("incoming.sbuf[5] = CAM_CMD_FLUSH;")
        destroy = mapped.index("incoming.sbuf[5] = CAM_CMD_DESTROY_SESSION;", flush)
        shutdown = mapped.index("== -ESHUTDOWN", destroy)
        retire = mapped.index("retire_query = 1;", shutdown)
        self.assertIn("reads == 5 && writes == 3 && !retire_acks", mapped[destroy:retire])
        self.assertIn("mt6878_ccd_mapped_worker_release(&owner) == -EBUSY", mapped[shutdown:retire])
        worker = (HERE / "worker-owner-test.c").read_text()
        self.assertIn("closed_session.first_error = -EINTR;", worker)
        self.assertIn("!closed_failed.retired && acknowledgments == previous_acknowledgments + 1", worker)


if __name__ == "__main__":
    unittest.main()
