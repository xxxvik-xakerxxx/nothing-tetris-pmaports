// SPDX-License-Identifier: GPL-2.0-only
/* CI compiles the canonical adapters, not a reimplementation of their TX/RX. */
#include "reset-host.h"
#include "mt6878-gpueb-sram-core.c"
#include "mt6878-gpueb-sram.c"
#include "mt6878-gpueb-reset.c"
#include <stdio.h>

static unsigned char *mock_sram;
static struct mt6878_gpueb_reset scope;
static struct device parent, client, stranger;
static struct module client_module;
static struct device_driver driver = { &client_module, 1 };
static u32 control[4];
static unsigned int reads, writes, sram_writes, doorbells, barriers, callbacks;
static unsigned int gpr_reads, change_second_gpr, immediate_consume;
static unsigned int callback_channel, callback_count;
static u32 callback_words[8];
static int claim_active;

static void *kzalloc(size_t bytes, int flags)
{ assert(flags == GFP_KERNEL); return calloc(1, bytes); }
static void kfree(void *pointer) { free(pointer); }
static struct resource *request_mem_region(uint64_t start, uint64_t size, const char *name)
{
	static struct resource res;
	assert(start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE && name);
	if (claim_active) return NULL;
	claim_active = 1;
	res = (struct resource){ start, start + size - 1, IORESOURCE_MEM };
	return &res;
}
static void release_mem_region(uint64_t start, uint64_t size)
{
	assert(claim_active && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE);
	claim_active = 0;
}
static void *ioremap(uint64_t start, uint64_t size)
{
	assert(claim_active && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE);
	mock_sram = malloc(size);
	assert(mock_sram);
	memset(mock_sram, 0xa5, size);
	return mock_sram;
}
static void iounmap(void *mapping)
{ assert(mapping == mock_sram); free(mapping); mock_sram = NULL; }

static void assert_transaction_locks(void)
{
	assert(pthread_mutex_trylock(&scope.lock.value) == EBUSY);
	assert(pthread_mutex_trylock(&scope.sram->lock.value) == EBUSY);
}
static uint32_t readl(const void *mapping)
{
	u32 value;
	assert_transaction_locks();
	reads++;
	if (mapping == mock_sram + GPUEB_GPR_OFFSET + 8) {
		gpr_reads++;
		if (change_second_gpr && gpr_reads == 2) return 0;
	}
	memcpy(&value, mapping, sizeof(value));
	return value;
}
static void writel(uint32_t word, void *mapping)
{
	uintptr_t addr = (uintptr_t)mapping;
	assert_transaction_locks();
	writes++;
	if (addr >= (uintptr_t)mock_sram && addr < (uintptr_t)mock_sram + GPUEB_SRAM_SIZE) {
		/* Only the first 216 TX bytes may be written by production code. */
		assert(addr >= (uintptr_t)mock_sram + GPUEB_MBOX_OFFSET);
		assert(addr + 4 <= (uintptr_t)mock_sram + GPUEB_MBOX_OFFSET + 216);
		sram_writes++;
		memcpy(mapping, &word, sizeof(word));
	} else if (mapping == &control[GPUEB_MBOX_SET]) {
		assert(barriers == doorbells + 1 && sram_writes);
		doorbells++;
		control[GPUEB_MBOX_SEND] |= word;
		if (immediate_consume) control[GPUEB_MBOX_SEND] &= ~word;
	} else {
		assert(mapping == &control[GPUEB_MBOX_CLR]);
		control[GPUEB_MBOX_RECV] &= ~word;
	}
}
static void fixture_barrier(void)
{ assert_transaction_locks(); barriers++; }

static void receive(void *context, unsigned int channel, const u32 *words, unsigned int count)
{
	assert(context == &scope && count <= 8);
	assert(!pthread_mutex_trylock(&scope.lock.value));
	assert(!pthread_mutex_unlock(&scope.lock.value));
	assert(!pthread_mutex_trylock(&scope.sram->lock.value));
	assert(!pthread_mutex_unlock(&scope.sram->lock.value));
	callbacks++;
	callback_channel = channel;
	callback_count = count;
	memcpy(callback_words, words, count * sizeof(*words));
	if (gpueb_channels[channel].recv_opt) {
		u32 tx[9] = { 0 };
		/* Test the in-flight guard, not a supported recursive callback API. */
		assert(scope.tx_inflight & BIT(channel));
		assert(mt6878_gpueb_reset_trysend(&scope, &client, channel, tx,
			gpueb_channels[channel].send_words) == -EBUSY);
	}
}

static void setup(void)
{
	struct resource res = { GPUEB_SRAM_BASE, GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1,
		IORESOURCE_MEM };
	u32 boot_word = 0x55667788;
	unsigned int i;
	memset(&scope, 0, sizeof(scope));
	memset(control, 0, sizeof(control));
	parent = (struct device){ .driver = &driver };
	client = (struct device){ .driver = &driver };
	stranger = (struct device){ .driver = &driver };
	client_module.refs = 0;
	mutex_init(&scope.lock);
	spin_lock_init(&scope.irq_lock);
	scope.parent = &parent;
	scope.parent_driver = parent.driver;
	scope.irq = 273;
	scope.sram = mt6878_gpueb_sram_create(&parent, &res);
	assert(!IS_ERR(scope.sram));
	scope.gpr = mt6878_gpueb_sram_get_window(scope.sram, GPUEB_WINDOW_GPR);
	scope.mbox = mt6878_gpueb_sram_get_window(scope.sram, GPUEB_WINDOW_MBOX);
	assert(!IS_ERR(scope.gpr) && !IS_ERR(scope.mbox));
	for (i = 0; i < 4; i++) scope.mbox_maps[i] = &control[i];
	memcpy(mock_sram + GPUEB_GPR_OFFSET + 8, &boot_word, sizeof(boot_word));
	reads = writes = sram_writes = doorbells = barriers = callbacks = 0;
	gpr_reads = change_second_gpr = immediate_consume = 0;
	fixture_masks = fixture_syncs = 0;
	fixture_irq_data.disabled = 1;
}
static void bind(unsigned int channel)
{
	assert(!mt6878_gpueb_reset_bind_channel(&scope, &client, channel, receive, &scope));
}
static void fixture_active(void)
{
	/* Private fixture construction ONLY. No production activation transition
	 * exists. Tests exercise future TX logic, not cold boot or IRQ readiness.
	 */
	scope.dispatch_active = true;
	fixture_irq_data.disabled = 0;
}
static void dispose(void)
{
	unsigned int i;
	mt6878_gpueb_sram_put_window(scope.gpr);
	mt6878_gpueb_sram_put_window(scope.mbox);
	if (scope.sram->core.phase == GPUEB_SRAM_QUARANTINED) {
		assert(mt6878_gpueb_sram_destroy(scope.sram) == -EBUSY);
		/* Mock disposal, never an added production quarantine escape. */
		iounmap(scope.sram->mapping);
		release_mem_region(GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE);
		put_device(scope.sram->parent);
		kfree(scope.sram);
	} else assert(!mt6878_gpueb_sram_destroy(scope.sram));
	for (i = 0; i < 11; i++) if (scope.registered & BIT(i)) {
		put_device(scope.channels[i].device);
		module_put(scope.channels[i].module);
	}
	assert(!parent.refs && !client.refs && !client_module.refs && !claim_active);
	assert(!pthread_mutex_destroy(&scope.lock.value));
	assert(!pthread_mutex_destroy(&scope.irq_lock));
}
static int send(unsigned int channel, const u32 *words)
{ return mt6878_gpueb_reset_trysend(&scope, &client, channel, words,
	gpueb_channels[channel].send_words); }
static void test_closed_and_identity(void)
{
	u32 words[9] = { 1 };
	setup(); bind(1);
	assert(!mt6878_gpueb_sram_check_parent(scope.sram, &parent));
	assert(mt6878_gpueb_sram_check_parent(scope.sram, &stranger) == -ENODEV);
	assert(send(1, words) == -EOPNOTSUPP);
	assert(!reads && !writes && !scope.first_error);
	fixture_irq_data.disabled = 0; /* External line enable is NOT authority. */
	assert(send(1, words) == -EOPNOTSUPP);
	assert(mailbox_irq_thread(273, &scope) == IRQ_HANDLED);
	assert(!reads && !writes);
	assert(fixture_masks == 1 && fixture_irq_data.disabled);
	assert(mt6878_gpueb_reset_trysend(&scope, &stranger, 1, words, 8) == -ENODEV);
	assert(mt6878_gpueb_reset_trysend(&scope, &client, 1, words, 9) == -EINVAL);
	assert(mt6878_gpueb_reset_trysend(&scope, &client, 11, words, 8) == -EINVAL);
	assert(!reads && !writes);
	fixture_active(); fixture_irq_data.disabled = 1;
	assert(send(1, words) == -EOPNOTSUPP);
	fixture_irq_data.disabled = 0;
	client.driver = NULL;
	assert(send(1, words) == -ENODEV);
	assert(scope.first_error == -ENODEV && fixture_masks == 1 && !reads && !writes);
	dispose();
}
static void test_all_slots(void)
{
	static const unsigned int offsets[] = { 0, 16, 48, 60, 84, 120, 136, 160, 184, 188, 204 };
	u32 words[9] = { 1, 2, 3, 4, 5, 6, 7, 8, 9 };
	unsigned int ch, i;
	for (ch = 0; ch < 11; ch++) {
		unsigned char expected[640];
		setup(); bind(ch); fixture_active();
		memset(expected, 0xa5, sizeof(expected));
		memcpy(expected + offsets[ch], words, gpueb_channels[ch].send_words * 4);
		assert(!send(ch, words));
		assert(gpr_reads == 2 && barriers == 1 && doorbells == 1);
		assert(sram_writes == gpueb_channels[ch].send_words && !callbacks);
		assert(control[GPUEB_MBOX_SEND] == BIT(ch));
		assert(!memcmp(expected, mock_sram + GPUEB_MBOX_OFFSET, sizeof(expected)));
		for (i = 0; i < GPUEB_GPR_SIZE; i++)
			if (i < 8 || i >= 12) assert(mock_sram[GPUEB_GPR_OFFSET + i] == 0xa5);
		assert(scope.tx_inflight == (gpueb_channels[ch].recv_opt ? BIT(ch) : 0));
		dispose();
	}
}
static void test_busy_and_actual_reply(void)
{
	u32 words[8] = { 1, 2, 3, 4, 5, 6, 7, 8 };
	unsigned int previous_writes;
	setup(); bind(1); fixture_active();
	control[GPUEB_MBOX_SEND] = BIT(1);
	assert(send(1, words) == -EBUSY && !writes && !scope.first_error);
	control[GPUEB_MBOX_SEND] = 0;
	immediate_consume = 1;
	assert(!send(1, words) && !control[GPUEB_MBOX_SEND]);
	assert(scope.tx_inflight == BIT(1) && !callbacks);
	previous_writes = writes;
	assert(send(1, words) == -EBUSY && writes == previous_writes);
	/* Clearing SEND did not invent a response. Supply real mocked RX instead. */
	memcpy(mock_sram + GPUEB_MBOX_OFFSET + 232, words, sizeof(words));
	control[GPUEB_MBOX_RECV] = BIT(1);
	assert(mailbox_irq_thread(273, &scope) == IRQ_HANDLED);
	assert(callbacks == 1 && callback_channel == 1 && callback_count == 8);
	assert(!memcmp(callback_words, words, sizeof(words)));
	assert(!scope.tx_inflight && !control[GPUEB_MBOX_RECV]);
	assert(!send(1, words));
	dispose();
}
static void test_faults_and_quiesce(void)
{
	u32 words[8] = { 1 }, zero = 0;
	unsigned int mode, previous_reads, previous_writes;
	for (mode = 0; mode < 4; mode++) {
		setup(); bind(1); fixture_active();
		if (mode == 0) memcpy(mock_sram + GPUEB_GPR_OFFSET + 8, &zero, 4);
		if (mode == 1) change_second_gpr = 1;
		if (mode == 2) control[GPUEB_MBOX_RECV] = BIT(1);
		if (mode == 3) assert(!mt6878_gpueb_sram_unknown_start(scope.sram));
		assert(send(1, words) == (mode < 2 ? -EHOSTDOWN :
			mode == 2 ? -EPROTO : -ESHUTDOWN));
		assert(sram_writes == (mode == 1 ? 8U : 0U) && !doorbells && !callbacks);
		assert(fixture_masks == 1 && scope.sram->core.phase == GPUEB_SRAM_QUARANTINED);
		previous_reads = reads; previous_writes = writes;
		assert(send(1, words) == scope.first_error);
		assert(reads == previous_reads && writes == previous_writes && fixture_masks == 1);
		dispose();
	}
	setup(); bind(1); fixture_active();
	assert(!mt6878_gpueb_reset_drain_irq(&scope));
	assert(!scope.dispatch_active && scope.dispatch_quiesced && fixture_syncs == 1);
	assert(send(1, words) == -ESHUTDOWN && !reads && !writes);
	assert(mailbox_irq_thread(273, &scope) == IRQ_HANDLED && !writes);
	dispose();
	setup(); bind(1); fixture_active();
	scope.reset_written = true; /* Fixture history, not a hardware reset write. */
	assert(send(1, words) == -ESHUTDOWN && !reads && !writes);
	dispose();
	setup(); bind(1); fixture_active();
	control[GPUEB_MBOX_RECV] = BIT(1); /* No owned TX: reject a stale ACK. */
	assert(mailbox_irq_thread(273, &scope) == IRQ_HANDLED);
	assert(scope.first_error == -EPROTO && !callbacks && !writes);
	dispose();
}
struct sender { int result; };
static void *concurrent_send(void *argument)
{
	struct sender *sender = argument;
	u32 words[8] = { 1 };
	sender->result = send(1, words);
	return NULL;
}
static void test_concurrent_send(void)
{
	struct sender senders[2];
	pthread_t threads[2];
	setup(); bind(1); fixture_active(); immediate_consume = 1;
	assert(!pthread_create(&threads[0], NULL, concurrent_send, &senders[0]));
	assert(!pthread_create(&threads[1], NULL, concurrent_send, &senders[1]));
	assert(!pthread_join(threads[0], NULL) && !pthread_join(threads[1], NULL));
	assert((senders[0].result == 0 && senders[1].result == -EBUSY) ||
		(senders[1].result == 0 && senders[0].result == -EBUSY));
	assert(doorbells == 1 && sram_writes == 8 && !callbacks);
	dispose();
}
int main(void)
{
	test_closed_and_identity(); test_all_slots(); test_busy_and_actual_reply();
	test_faults_and_quiesce(); test_concurrent_send();
	puts("Canonical GPU TX/RX fixture PASS: mocked MMIO only; activation is NOT proven");
	return 0;
}
