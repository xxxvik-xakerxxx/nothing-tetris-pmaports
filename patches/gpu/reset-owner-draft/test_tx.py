#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic exact-source TX checks; no native compilation/execution."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_native import definition
from test_gpueb_power import vendor
from test_gpueb_session import vendor_tables


class Transmit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reset = (HERE / "mt6878-gpueb-reset.c").read_text()
        cls.sram = (HERE.parent / "sram-owner/mt6878-gpueb-sram.c").read_text()
        cls.core = (HERE.parent / "sram-owner/mt6878-gpueb-sram-core.c").read_text()

    def test_exact_pinned_send_and_completion_sources(self):
        evidence = json.loads((HERE / "RESOURCE-CONTRACT.json").read_text())
        for path in ("drivers/rpmsg/mtk_rpmsg_mbox.c",
                     "drivers/soc/mediatek/mtk_tinysys_ipi.c"):
            self.assertEqual(hashlib.sha256(vendor(path).encode()).hexdigest(),
                             evidence["source"]["files_sha256"][path])
        send = definition(vendor("drivers/rpmsg/mtk_rpmsg_mbox.c"), "int mtk_mbox_send(")
        self.assertLess(send.index("mtk_mbox_check_send_irq("), send.index("mtk_mbox_write("))
        self.assertLess(send.index("mtk_mbox_write("), send.index("mb();"))
        self.assertLess(send.index("mb();"), send.index("mtk_mbox_trigger_irq("))
        self.assertIn("0x1 << mchan->send_pin_index", send)
        self.assertIn("len * MBOX_SLOT_SIZE", send)
        ack = definition(vendor("drivers/soc/mediatek/mtk_tinysys_ipi.c"), "int mtk_ipi_send_compl(")
        self.assertIn("wait_for_completion_timeout(&pin_r->notify", ack)
        self.assertIn("try_wait_for_completion(&pin_r->notify)", ack)
        self.assertIn("MBOX_RECV_ACK      = 1", vendor("include/linux/soc/mediatek/mtk-mbox.h"))

    def test_full_slot_packing_matches_all_eleven_vendor_channels(self):
        _, (send, _) = vendor_tables()
        slot = definition(self.core, "int gpueb_sram_tx_slot(")
        widths = [int(v) for v in re.search(r"words\[\] = \{ ([\d, ]+) \}", slot)[1].split(",")]
        self.assertEqual(widths, [row[2] for row in send])
        self.assertEqual(sum(widths) * 4, 216)
        offsets = []
        for width in widths:
            offsets.append(sum(widths[:len(offsets)]) * 4)
        fixture = (HERE / "test-mailbox.c").read_text()
        expected = [int(v) for v in re.search(r"offsets\[\] = \{ ([\d, ]+) \}", fixture)[1].split(",")]
        self.assertEqual(expected, offsets)
        self.assertIn("count != words[channel]", slot)
        self.assertIn("channel >= sizeof(words) / sizeof(words[0])", slot)

    def test_only_fixed_sram_write_after_preflight_and_before_commit(self):
        send = definition(self.sram, "int mt6878_gpueb_sram_send_transaction(")
        for token in ("gpr->sram != mbox->sram", "gpr->type != GPUEB_WINDOW_GPR",
                      "mbox->type != GPUEB_WINDOW_MBOX", "gpueb_sram_tx_slot(channel, count, &offset)"):
            self.assertIn(token, send)
        self.assertLess(send.index("mutex_lock("), send.index("gpueb_sram_window_range("))
        self.assertLess(send.rindex("gpueb_sram_window_range("), send.index("before(&reader, context)"))
        self.assertLess(send.index("before(&reader, context)"), send.index("writel(words[i]"))
        self.assertLess(send.index("writel(words[i]"), send.index("commit(&reader, context)"))
        self.assertLess(send.index("commit(&reader, context)"), send.index("mutex_unlock("))
        self.assertEqual(self.sram.count("writel("), 1)
        header = (HERE.parent / "sram-owner/mt6878-gpueb-sram.h").read_text()
        api = header.split("int mt6878_gpueb_sram_send_transaction(", 1)[1].split(";", 1)[0]
        self.assertNotIn("offset", api)
        self.assertNotIn("__iomem", header)

    def test_scope_gates_real_client_irq_and_owner_before_transaction(self):
        send = definition(self.reset, "int mt6878_gpueb_reset_trysend(")
        for token in ("scope->first_error", "scope->dispatch_quiesced || scope->reset_written",
                      "scope->channels[channel].device != client",
                      "client->driver != scope->channels[channel].driver",
                      "scope->parent->driver != scope->parent_driver",
                      "irq_get_irq_data(scope->irq)", "irqd_irq_disabled(irq_data)",
                      "!scope->dispatch_active", "scope->irq_contained", "scope->tx_inflight & BIT(channel)"):
            self.assertIn(token, send)
            self.assertLess(send.index(token), send.index("mt6878_gpueb_sram_send_transaction("))
        self.assertLess(send.index("mutex_lock("), send.index("scope->first_error"))
        self.assertLess(send.index("mt6878_gpueb_sram_send_transaction("), send.index("mutex_unlock("))
        self.assertIn("ret = -EOPNOTSUPP", send)
        self.assertIn("count != gpueb_channels[channel].send_words", send)
        self.assertIn("memcpy(payload, words", send)
        prepare = definition(self.reset, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        self.assertLess(prepare.index("mt6878_gpueb_sram_check_parent(sram, &parent->dev)"),
                        prepare.index("pm_runtime_get_if_in_use("))
        check = definition(self.sram, "int mt6878_gpueb_sram_check_parent(")
        self.assertIn("sram->parent != parent ? -ENODEV", check)
        self.assertIn("sram->core.phase != GPUEB_SRAM_OWNED ? -ESHUTDOWN", check)
        # No production path can turn activation provenance on.
        self.assertNotRegex(self.reset, r"dispatch_active\s*=\s*(?:true|1)")
        header = (HERE / "mt6878-gpueb-reset.h").read_text()
        self.assertNotRegex(header, r"bool\s+(?:ready|active|enabled)")

    def test_two_actual_boot_reads_status_barrier_and_single_doorbell(self):
        before = definition(self.reset, "static int tx_before(")
        commit = definition(self.reset, "static int tx_commit(")
        actual = "mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1)"
        for code in (before, commit):
            self.assertEqual(code.count(actual), 1)
            self.assertIn("boot_word != 0x55667788", code)
        self.assertIn("readl(scope->mbox_maps[GPUEB_MBOX_SEND]) & BIT(tx->channel)", before)
        self.assertIn("ret", before)
        self.assertIn("return -EBUSY", before)
        self.assertIn("readl(scope->mbox_maps[GPUEB_MBOX_RECV]) & BIT(tx->channel)", before)
        self.assertLess(commit.index(actual), commit.index("mb();"))
        self.assertLess(commit.index("mb();"), commit.index("scope->tx_inflight |= BIT(tx->channel)"))
        self.assertLess(commit.index("scope->tx_inflight |= BIT(tx->channel)"), commit.index("writel("))
        self.assertLess(commit.index("writel("), commit.index("readl(scope->mbox_maps[GPUEB_MBOX_SEND])"))
        self.assertEqual(commit.count("writel("), 1)
        self.assertIn("writel(BIT(tx->channel), scope->mbox_maps[GPUEB_MBOX_SET])", commit)
        for forbidden in ("GPUEB_MBOX_CLR", "complete(", "while (", "udelay(", "msleep("):
            self.assertNotIn(forbidden, before + commit)
        self.assertNotIn("-EBUSY", commit)  # Only pre-write busy is non-sticky.

    def test_real_rx_retires_inflight_only_after_callback(self):
        snapshot = definition(self.reset, "static int snapshot_mailbox(")
        self.assertIn("!(scope->tx_inflight & BIT(i))", snapshot)
        self.assertLess(snapshot.index("snapshot->replies |= BIT(i)"), snapshot.index("writel(pending,"))
        self.assertNotIn("tx_inflight &=", snapshot)
        thread = definition(self.reset, "static irqreturn_t mailbox_irq_thread(")
        self.assertLess(thread.index("scope->channels[i].receive("), thread.index("scope->tx_inflight &= ~snapshot.replies"))
        self.assertLess(thread.rindex("mutex_lock(&scope->lock)"), thread.index("scope->tx_inflight &= ~snapshot.replies"))
        self.assertNotIn("tx_inflight &=", definition(self.reset, "static int tx_commit("))

    def test_first_fault_no_retry_or_activation_side_effects(self):
        send = definition(self.reset, "int mt6878_gpueb_reset_trysend(")
        self.assertEqual(send.count("mt6878_gpueb_sram_send_transaction("), 1)
        self.assertIn("if (!ret || ret == -EBUSY)", send)
        self.assertIn("contain_irq(scope, ret)", send)
        self.assertIn("ret = READ_ONCE(scope->first_error)", send)
        for code in (send, definition(self.reset, "static int tx_before("),
                     definition(self.reset, "static int tx_commit(")):
            for forbidden in ("enable_irq(", "complete(", "arm_smccc", "rproc_boot(", "memset_io(", "memcpy_toio("):
                self.assertNotIn(forbidden, code)
        drain = definition(self.reset, "int mt6878_gpueb_reset_drain_irq(")
        self.assertLess(drain.index("scope->dispatch_active = false"), drain.index("mask_irq_once(scope)"))

    def test_fixture_uses_canonical_implementations_and_is_ci_only(self):
        fixture = (HERE / "test-mailbox.c").read_text()
        for name in ("mt6878-gpueb-reset.c", "mt6878-gpueb-sram.c", "mt6878-gpueb-sram-core.c"):
            self.assertIn('#include "' + name + '"', fixture)
        for token in ("test_closed_and_identity", "test_all_slots", "test_busy_and_actual_reply",
                      "test_faults_and_quiesce", "test_concurrent_send", "pthread_create",
                      "assert_transaction_locks", "change_second_gpr", "immediate_consume"):
            self.assertIn(token, fixture)
        script = HERE / "run-native-ci.sh"
        self.assertEqual(subprocess.run(["sh", "-n", str(script)], capture_output=True).returncode, 0)
        for ci, actions in (("false", "false"), ("true", "false"), ("false", "true")):
            result = subprocess.run(["sh", str(script)],
                                    env=dict(os.environ, CI=ci, GITHUB_ACTIONS=actions, CC="/nonexistent"),
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("CI-only", result.stderr)


if __name__ == "__main__":
    unittest.main()
