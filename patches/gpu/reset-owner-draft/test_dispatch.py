#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned layout and native dispatcher source checks, never C execution.

These checks catch wiring/order/layout regressions. They do not execute the
IRQ, establish firmware provenance, or prove Linux scheduling/fault behavior.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
GPU = HERE.parent
sys.path.insert(0, str(GPU))
from prepare_native import definition
from test_gpueb_power import vendor, ROOT
from test_gpueb_session import vendor_tables


def channel_rows(code):
    table = code.split("} gpueb_channels[] = {", 1)[1].split("};", 1)[0]
    return [tuple(int(cell) for cell in row.split(","))
            for row in re.findall(r"\{ ([\d, ]+) \}", table)]


def expected_rows():
    _, (send, recv) = vendor_tables()
    offset = sum(row[2] * 4 for row in send)
    result = []
    for tx, rx in zip(send, recv):
        result.append((tx[2], rx[2], rx[3], rx[4], offset))
        offset += rx[2] * 4
    return result


class Dispatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reset = (HERE / "mt6878-gpueb-reset.c").read_text()
        cls.sram = (GPU / "sram-owner/mt6878-gpueb-sram.c").read_text()
        cls.provider = (GPU / "reset-provider-draft/mt6878-gpueb-reset-provider.c").read_text()
        cls.control = (GPU / "bound-parent-draft/mt6878-gpueb-control.c").read_text()

    def test_source_identity_and_status_ack_contract(self):
        evidence = json.loads((HERE / "RESOURCE-CONTRACT.json").read_text())
        for path in ("drivers/soc/mediatek/mtk-mbox.c",
                     "drivers/gpu/mediatek/gpueb/gpueb_ipi.c",
                     "arch/arm64/boot/dts/mediatek/mt6878.dts"):
            code = vendor(path)
            self.assertEqual(hashlib.sha256(code.encode()).hexdigest(),
                             evidence["source"]["files_sha256"][path])
        mbox = vendor("drivers/soc/mediatek/mtk-mbox.c")
        read = definition(mbox, "unsigned int mtk_mbox_read_recv_irq(")
        clear = definition(mbox, "int mtk_mbox_clr_irq(")
        self.assertIn("reg = readl(minfo->recv_status_reg)", read)
        self.assertIn("writel(irq, minfo->clr_irq_reg)", clear)
        isr = definition(mbox, "static irqreturn_t mtk_mbox_isr(")
        self.assertLess(isr.index("ret = mtk_mbox_read(mbdev, mbox"),
                        isr.index("mtk_mbox_clr_irq(mbdev, mbox, irq_temp)"))

    def test_all_eleven_channels_match_source_and_fit_snapshot(self):
        expected = expected_rows()
        actual = channel_rows(self.reset)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 11)
        self.assertEqual(actual[1], (8, 8, 1, 1, 232))
        self.assertEqual(actual[-1][-1] + actual[-1][1] * 4, 352)
        self.assertLessEqual(max(row[1] for row in actual), 8)
        self.assertLessEqual(actual[-1][-1] + actual[-1][1] * 4, 640)

    def test_profile_preflight_covers_complete_tables_before_power(self):
        validate = definition(self.reset, "static int validate_mailbox_layout(")
        for prop in ("mbox-count", "mbox-size", "slot-size", "ts-mbox",
                     "send-table", "recv-table"):
            self.assertIn('"' + prop + '"', validate)
        self.assertIn("GPUEB_MBOX_CHANNELS * 3", validate)
        self.assertIn("GPUEB_MBOX_CHANNELS * 5", validate)
        self.assertEqual(validate.count("value != expected"), 2)
        self.assertIn("const u32 send[] = { i, 0, gpueb_channels[i].send_words }", validate)
        self.assertIn("const u32 recv[] = { i, 0, gpueb_channels[i].recv_words,", validate)
        self.assertIn("gpueb_channels[i].recv_opt, gpueb_channels[i].cb_opt", validate)
        self.assertIn("expected = send[j]", validate)
        self.assertIn("expected = recv[j]", validate)
        self.assertIn("return validate_mailbox_layout(parent->dev.of_node)", self.reset)
        prepare = definition(self.control, "int mt6878_gpueb_control_prepare(")
        self.assertLess(prepare.index("mt6878_gpueb_reset_validate_resources(parent)"),
                        prepare.index("mt6878_gpueb_mfg0_resume("))

    def test_root_provider_scope_chain_and_fixed_client_pins(self):
        root = definition(self.control, "int mt6878_gpueb_control_bind_channel(")
        provider = definition(self.provider, "int mt6878_gpueb_reset_provider_bind_channel(")
        bind = definition(self.reset, "int mt6878_gpueb_reset_bind_channel(")
        self.assertIn("control->first_error", root)
        self.assertIn("!control->reset || control->power", root)
        self.assertIn("mt6878_gpueb_reset_provider_bind_channel(control->reset", root)
        self.assertIn("mt6878_gpueb_reset_bind_channel(provider->scope", provider)
        self.assertLess(provider.index("provider->asserted"), provider.index("mt6878_gpueb_reset_bind_channel("))
        for token in ("channel >= GPUEB_MBOX_CHANNELS", "!client->driver->suppress_bind_attrs",
                      "scope->registered & BIT(channel)", "return -EINVAL;", "ret = -EBUSY;",
                      "scope->dispatch_quiesced || scope->reset_written"):
            self.assertIn(token, bind)
        self.assertLess(bind.index("try_module_get(module)"), bind.index("get_device(client)"))
        self.assertLess(bind.index(".receive = receive"), bind.index("scope->registered |= BIT(channel)"))

    def test_real_thread_is_requested_by_existing_exclusive_owner(self):
        prepare = definition(self.reset, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        self.assertIn("request_threaded_irq(irq, NULL, mailbox_irq_thread", prepare)
        self.assertIn("IRQF_ONESHOT | IRQF_NO_AUTOEN", prepare)
        self.assertLess(prepare.index("scope->mbox_claims++"), prepare.index("scope->mbox_maps[i] = ioremap("))
        self.assertLess(prepare.index("scope->mbox_maps[i] = ioremap("), prepare.index("request_threaded_irq("))
        self.assertEqual(self.reset.count("request_threaded_irq("), 1)
        for source in (self.reset, self.provider, self.control):
            self.assertNotIn("IRQF_SHARED", re.sub(r"/\*.*?\*/", "", source, flags=re.S))
        for source in (self.provider, self.control):
            for token in ("request_threaded_irq(", "ioremap(", "request_mem_region("):
                self.assertNotIn(token, source)

    def test_irq_snapshot_gates_actual_gpr_twice_before_single_ack(self):
        snapshot = definition(self.reset, "static int snapshot_mailbox(")
        actual_gpr = "mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1)"
        self.assertEqual(snapshot.count(actual_gpr), 2)
        self.assertEqual(snapshot.count("boot_word != 0x55667788"), 2)
        self.assertIn("if (pending & ~scope->registered)\n\t\treturn -EPROTO;", snapshot)
        self.assertIn("if (!(pending & BIT(i)))\n\t\t\tcontinue;", snapshot)
        copy = snapshot.index("snapshot->payload[i], gpueb_channels[i].recv_words")
        ack = snapshot.index("writel(pending, scope->mbox_maps[GPUEB_MBOX_CLR])")
        self.assertLess(snapshot.index("pending & ~scope->registered"), copy)
        self.assertLess(copy, snapshot.rindex(actual_gpr))
        self.assertLess(snapshot.rindex("boot_word != 0x55667788"), ack)
        self.assertLess(ack, snapshot.rindex("readl(scope->mbox_maps[GPUEB_MBOX_RECV])"))
        self.assertLess(ack, snapshot.index("snapshot->pending = pending"))
        self.assertEqual(snapshot.count("writel("), 1)
        for token in ("scope->ready", "boot_ready =", "session_ready =", "0x34", "GPUEB_MBOX_SET"):
            self.assertNotIn(token, snapshot)

    def test_quarantine_excluded_for_whole_snapshot_and_ack(self):
        transaction = definition(self.sram, "int mt6878_gpueb_sram_read_transaction(")
        for token in ("gpr->sram != mbox->sram", "gpr->type != GPUEB_WINDOW_GPR",
                      "mbox->type != GPUEB_WINDOW_MBOX"):
            self.assertIn(token, transaction)
        self.assertEqual(transaction.count("gpueb_sram_window_range("), 2)
        self.assertLess(transaction.index("mutex_lock(&reader.sram->lock)"),
                        transaction.index("gpueb_sram_window_range("))
        self.assertLess(transaction.rindex("gpueb_sram_window_range("), transaction.index("consume(&reader, context)"))
        self.assertLess(transaction.index("consume(&reader, context)"), transaction.index("mutex_unlock(&reader.sram->lock)"))
        quarantine = definition(self.sram, "int mt6878_gpueb_sram_unknown_start(")
        self.assertLess(quarantine.index("mutex_lock(&sram->lock)"), quarantine.index("gpueb_sram_quarantine("))
        thread = definition(self.reset, "static irqreturn_t mailbox_irq_thread(")
        self.assertIn("snapshot_mailbox, &snapshot", thread)
        self.assertLess(thread.index("mutex_lock(&scope->lock)"), thread.index("mt6878_gpueb_sram_read_transaction("))
        copied = thread.index("mt6878_gpueb_sram_read_transaction(")
        unlocked = thread.index("mutex_unlock(&scope->lock)", copied)
        self.assertLess(copied, unlocked)
        self.assertLess(unlocked, thread.index("scope->channels[i].receive("))

    def test_read_accessor_is_bounded_and_uses_only_sole_mapping(self):
        read = definition(self.sram, "int mt6878_gpueb_sram_reader_words(")
        self.assertLess(read.index("count > GPUEB_MBOX_SIZE / sizeof(*words)"),
                        read.index("(u64)count * sizeof(*words)"))
        self.assertLess(read.index("gpueb_sram_window_range("), read.index("if (!ret)"))
        self.assertLess(read.index("if (!ret)"), read.index("readl(sram->mapping"))
        self.assertIn("range.start - sram->core.whole.start", read)
        self.assertNotIn("ioremap(", read)
        self.assertNotIn("writel(", read)
        send = definition(self.sram, "int mt6878_gpueb_sram_send_transaction(")
        self.assertEqual(self.sram.count("writel("), send.count("writel("))
        self.assertEqual(self.sram.count("ioremap("), 1)
        core = (GPU / "sram-owner/mt6878-gpueb-sram-core.c").read_text()
        bounds = definition(core, "int gpueb_sram_window_range(")
        self.assertIn("core->phase != GPUEB_SRAM_OWNED", bounds)
        self.assertIn("size > capacity - offset", bounds)

    def test_quiesce_masks_and_waits_outside_thread_mutex_before_reset(self):
        thread = definition(self.reset, "static irqreturn_t mailbox_irq_thread(")
        quiet = thread.split("if (scope->dispatch_quiesced) {", 1)[1].split("}", 1)[0]
        self.assertIn("mutex_unlock(&scope->lock)", quiet)
        self.assertIn("return IRQ_HANDLED", quiet)
        for forbidden in ("contain_irq", "latch(", "writel(", ".receive("):
            self.assertNotIn(forbidden, quiet)
        self.assertLess(thread.index("if (ret)"), thread.index("if (scope->dispatch_quiesced)"))
        drain = definition(self.reset, "int mt6878_gpueb_reset_drain_irq(")
        self.assertLess(drain.index("scope->dispatch_quiesced = true"), drain.index("mask_irq_once(scope)"))
        self.assertLess(drain.index("mask_irq_once(scope)"), drain.index("mutex_unlock(&scope->lock)"))
        self.assertLess(drain.index("mutex_unlock(&scope->lock)"), drain.index("synchronize_irq("))
        self.assertLess(drain.index("synchronize_irq("), drain.rindex("mutex_lock(&scope->lock)"))
        hold = definition(self.reset, "int mt6878_gpueb_reset_hold(")
        self.assertLess(hold.index("mt6878_gpueb_reset_drain_irq(scope)"), hold.index("writel(0,"))
        destroy = definition(self.reset, "int mt6878_gpueb_reset_destroy(")
        self.assertLess(destroy.index("mt6878_gpueb_reset_drain_irq(scope)"), destroy.index("free_irq("))
        self.assertLess(destroy.index("return ret ?: -EBUSY"), destroy.index("free_irq("))
        self.assertLess(destroy.rindex("mutex_unlock(&scope->lock)"), destroy.index("free_irq("))
        self.assertLess(destroy.index("free_irq("), destroy.index("put_device(scope->channels[i].device)"))
        self.assertLess(destroy.index("module_put(scope->channels[i].module)"), destroy.index("release_mailbox_resources("))

    def test_fault_preserves_error_disables_once_and_never_acks(self):
        contain = definition(self.reset, "static void contain_irq(")
        self.assertLess(contain.index("latch(scope, error)"), contain.index("mask_irq_once(scope)"))
        self.assertIn("mt6878_gpueb_sram_unknown_start(scope->sram)", contain)
        self.assertNotIn("writel(", contain)
        mask = definition(self.reset, "static void mask_irq_once(")
        self.assertIn("disable = !scope->irq_contained", mask)
        self.assertIn("if (disable)\n\t\tdisable_irq_nosync(scope->irq)", mask)
        latch = definition(self.reset, "static int latch(")
        self.assertIn("if (!scope->first_error)", latch)
        thread = definition(self.reset, "static irqreturn_t mailbox_irq_thread(")
        self.assertLess(thread.index("if (scope->reset_written)"),
                        thread.index("mt6878_gpueb_sram_read_transaction("))
        fault = thread.split("fault:\n", 1)[1]
        self.assertNotIn(".receive(", fault)
        self.assertNotIn("writel(", fault)

    def test_no_activation_api_or_fabricated_ready(self):
        for source in (self.reset, self.provider, self.control, self.sram):
            for token in ("enable_irq(", "memcpy_toio(", "memset_io(",
                          "0x3f00000b", "arm_smccc", "rproc_boot(", "ready = true"):
                self.assertNotIn(token, source)
        header = (HERE / "mt6878-gpueb-reset.h").read_text()
        self.assertNotIn("bool ready", header)
        self.assertIn("Binding does not enable the IRQ", header)

    def test_target_linux_thread_context_and_full_thread_drain(self):
        tree = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        kernel = (tree / "kernel/irq/manage.c").read_text()
        request = definition(kernel, "int request_threaded_irq(")
        primary = definition(kernel, "static irqreturn_t irq_default_primary_handler(")
        explicit = definition(kernel, "static irqreturn_t irq_thread_fn(")
        forced = definition(kernel, "static int irq_setup_forced_threading(")
        sync = definition(kernel, "static void __synchronize_irq(")
        self.assertIn("handler = irq_default_primary_handler", request)
        self.assertIn("action->thread_fn = thread_fn", request)
        self.assertIn("return IRQ_WAKE_THREAD", primary)
        self.assertIn("action->thread_fn(action->irq, action->dev_id)", explicit)
        for token in ("local_bh_disable(", "local_irq_disable(", "raw_spin_lock"):
            self.assertNotIn(token, explicit)
        self.assertIn("IRQF_NO_THREAD | IRQF_PERCPU | IRQF_ONESHOT", forced)
        self.assertIn("if (!(new->flags & IRQF_NO_AUTOEN)", kernel)
        self.assertIn("__synchronize_hardirq(desc, true)", sync)
        self.assertIn("wait_event(desc->wait_for_threads, !atomic_read(&desc->threads_active))", sync)
        snapshot = definition(self.reset, "static int snapshot_mailbox(")
        for token in ("mutex_lock(", "wait_for_completion", "synchronize_irq(", "free_irq("):
            self.assertNotIn(token, snapshot)
        mask = definition(self.reset, "static void mask_irq_once(")
        self.assertLess(mask.index("spin_unlock_irqrestore("), mask.index("disable_irq_nosync("))


if __name__ == "__main__":
    unittest.main()
