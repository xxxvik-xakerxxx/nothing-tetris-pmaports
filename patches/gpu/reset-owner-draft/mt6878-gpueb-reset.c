// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_RESET_HOST_TEST
#include "reset-host.h"
#else
#include <linux/device.h>
#include <linux/err.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/irq.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>
#endif
#include "mt6878-gpueb-sram.h"
#include "mt6878-gpueb-reset.h"

enum { GPUEB_MBOX_CONTROL_FIRST = 4, GPUEB_MBOX_CONTROL_COUNT = 4,
	GPUEB_MBOX_CHANNELS = 11, GPUEB_MBOX_MAX_RX_WORDS = 8,
	GPUEB_MBOX_MAX_TX_WORDS = 9 };
enum { GPUEB_MBOX_SET, GPUEB_MBOX_CLR, GPUEB_MBOX_SEND, GPUEB_MBOX_RECV };

/* ee2be53 send-table then recv-table, in four-byte slots. */
static const struct {
	u32 send_words, recv_words, recv_opt, cb_opt, recv_offset;
} gpueb_channels[] = {
	{ 4, 4, 0, 0, 216 },
	{ 8, 8, 1, 1, 232 },
	{ 3, 1, 0, 1, 264 },
	{ 6, 1, 0, 1, 268 },
	{ 9, 1, 1, 1, 272 },
	{ 4, 4, 1, 1, 276 },
	{ 6, 1, 1, 1, 292 },
	{ 6, 6, 1, 1, 296 },
	{ 1, 4, 0, 1, 320 },
	{ 4, 1, 1, 1, 336 },
	{ 3, 3, 1, 1, 340 },
};

static int validate_mailbox_layout(struct device_node *node)
{
	u32 value, expected;
	unsigned int i, j;
	static const struct { const char *name; u32 value; } scalars[] = {
		{ "mbox-count", 1 }, { "mbox-size", 160 },
		{ "slot-size", 4 }, { "ts-mbox", 0 },
	};

	for (i = 0; i < ARRAY_SIZE(scalars); i++)
		if (of_property_count_u32_elems(node, scalars[i].name) != 1 ||
		    of_property_read_u32(node, scalars[i].name, &value) ||
		    value != scalars[i].value)
			return -EINVAL;
	if (of_property_count_u32_elems(node, "send-table") != GPUEB_MBOX_CHANNELS * 3 ||
	    of_property_count_u32_elems(node, "recv-table") != GPUEB_MBOX_CHANNELS * 5)
		return -EINVAL;
	for (i = 0; i < GPUEB_MBOX_CHANNELS; i++) {
		const u32 send[] = { i, 0, gpueb_channels[i].send_words };
		const u32 recv[] = { i, 0, gpueb_channels[i].recv_words,
			gpueb_channels[i].recv_opt, gpueb_channels[i].cb_opt };

		for (j = 0; j < 3; j++) {
			expected = send[j];
			if (of_property_read_u32_index(node, "send-table", i * 3 + j, &value) ||
			    value != expected)
				return -EINVAL;
		}
		for (j = 0; j < 5; j++) {
			expected = recv[j];
			if (of_property_read_u32_index(node, "recv-table", i * 5 + j, &value) ||
			    value != expected)
				return -EINVAL;
		}
	}
	return 0;
}

/* ee2be53 MT6878 DT. GPR/data are aliases inside the sole SRAM claim;
 * the four mailbox control words are OUTSIDE the separate reset bank.
 */
static const struct {
	const char *name;
	resource_size_t start, size;
} gpueb_resources[] = {
	{ "gpueb_base", GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE },
	{ "gpueb_gpr_base", GPUEB_SRAM_BASE + GPUEB_GPR_OFFSET, GPUEB_GPR_SIZE },
	{ "gpueb_reg_base", 0x13c60000, 0x2000 },
	{ "mbox0_base", GPUEB_SRAM_BASE + GPUEB_MBOX_OFFSET, GPUEB_MBOX_SIZE },
	{ "mbox0_set", 0x13c62004, 0x4 },
	{ "mbox0_clr", 0x13c62074, 0x4 },
	{ "mbox0_send", 0x13c62000, 0x4 },
	{ "mbox0_recv", 0x13c62078, 0x4 },
};

int mt6878_gpueb_reset_validate_resources(struct platform_device *parent)
{
	struct resource *resource;
	unsigned int i, count = 0;

	if (!parent || !parent->dev.of_node)
		return -EINVAL;
	if (!of_device_is_available(parent->dev.of_node) ||
	    !of_device_is_compatible(parent->dev.of_node, "mediatek,gpueb"))
		return -ENODEV;
	for (i = 0; i < parent->num_resources; i++)
		if (resource_type(&parent->resource[i]) == IORESOURCE_MEM)
			count++;
	if (count != ARRAY_SIZE(gpueb_resources))
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(gpueb_resources); i++) {
		resource = platform_get_resource_byname(parent, IORESOURCE_MEM,
						gpueb_resources[i].name);
		/* Compare endpoints with a bounded static profile, avoiding size
		 * arithmetic on possibly reversed or wrapping supplied resources.
		 */
		if (!resource || resource->start != gpueb_resources[i].start ||
		    resource->end != gpueb_resources[i].start + gpueb_resources[i].size - 1)
			return -ERANGE;
	}
	return validate_mailbox_layout(parent->dev.of_node);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_validate_resources);

struct mt6878_gpueb_reset {
	struct device *parent;
	struct device_driver *parent_driver;
	struct mt6878_gpueb_sram *sram;
	struct mt6878_gpueb_window *gpr, *mbox;
	void __iomem *registers;
	struct resource *mbox_control[GPUEB_MBOX_CONTROL_COUNT];
	void __iomem *mbox_maps[GPUEB_MBOX_CONTROL_COUNT];
	struct {
		struct device *device;
		struct module *module;
		struct device_driver *driver;
		mt6878_gpueb_receive_t receive;
		void *context;
	} channels[GPUEB_MBOX_CHANNELS];
	u32 registered, tx_inflight;
	unsigned int mbox_claims;
	struct mutex lock;
	spinlock_t irq_lock;
	int irq, first_error;
	bool reset_written, dispatch_quiesced, irq_contained;
	/* Private activation provenance, never a caller-supplied permission. No
	 * production setter exists until cold-start/IRQ lifecycle is implemented.
	 */
	bool dispatch_active;
};

static void release_mailbox_resources(struct mt6878_gpueb_reset *scope)
{
	struct resource *resource;

	while (scope->mbox_claims) {
		unsigned int i = --scope->mbox_claims;

		if (scope->mbox_maps[i])
			iounmap(scope->mbox_maps[i]);
		resource = scope->mbox_control[i];
		release_mem_region(resource->start, resource_size(resource));
	}
}

static int latch(struct mt6878_gpueb_reset *scope, int error)
{
	unsigned long flags;
	int ret;
	spin_lock_irqsave(&scope->irq_lock, flags);
	if (!scope->first_error)
		scope->first_error = error;
	ret = scope->first_error;
	spin_unlock_irqrestore(&scope->irq_lock, flags);
	return ret;
}

static void mask_irq_once(struct mt6878_gpueb_reset *scope)
{
	unsigned long flags;
	bool disable;

	spin_lock_irqsave(&scope->irq_lock, flags);
	disable = !scope->irq_contained;
	scope->irq_contained = true;
	spin_unlock_irqrestore(&scope->irq_lock, flags);
	if (disable)
		disable_irq_nosync(scope->irq);
}

static void contain_irq(struct mt6878_gpueb_reset *scope, int error)
{
	latch(scope, error);
	mask_irq_once(scope);
	mt6878_gpueb_sram_unknown_start(scope->sram);
}

struct gpueb_irq_snapshot {
	struct mt6878_gpueb_reset *scope;
	u32 payload[GPUEB_MBOX_CHANNELS][GPUEB_MBOX_MAX_RX_WORDS];
	u32 pending;
	u32 replies;
};

/* Runs with BOTH scope and whole-SRAM mutexes held, including the ACK. */
static int snapshot_mailbox(struct mt6878_gpueb_reader *reader, void *data)
{
	struct gpueb_irq_snapshot *snapshot = data;
	struct mt6878_gpueb_reset *scope = snapshot->scope;
	u32 pending, boot_word;
	unsigned int i;
	int ret;

	/* BOOTREADY is read from the sole GPR lease every time. It neither proves
	 * cold-start provenance nor replaces GPUFREQ's separate GPR13 handshake.
	 */
	ret = mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1);
	if (ret)
		return ret;
	if (boot_word != 0x55667788)
		return -EHOSTDOWN;
	pending = readl(scope->mbox_maps[GPUEB_MBOX_RECV]);
	if (!pending)
		return 0;
	/* Unregistered/unknown bits are never silently ACKed or discarded. */
	if (pending & ~scope->registered)
		return -EPROTO;
	for (i = 0; i < GPUEB_MBOX_CHANNELS; i++)
		if ((pending & BIT(i)) && gpueb_channels[i].recv_opt) {
			/* A stale/unowned reply is not a new command's ACK. */
			if (!(scope->tx_inflight & BIT(i)))
				return -EPROTO;
			snapshot->replies |= BIT(i);
		}
	for (i = 0; i < GPUEB_MBOX_CHANNELS; i++) {
		if (!(pending & BIT(i)))
			continue;
		ret = mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_MBOX,
				gpueb_channels[i].recv_offset,
				snapshot->payload[i], gpueb_channels[i].recv_words);
		if (ret)
			return ret;
	}
	ret = mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1);
	if (ret)
		return ret;
	if (boot_word != 0x55667788)
		return -EHOSTDOWN;
	/* All pending payloads are now local. Clear only this captured mask,
	 * then flush the posted clear through the same source-backed status word.
	 */
	writel(pending, scope->mbox_maps[GPUEB_MBOX_CLR]);
	readl(scope->mbox_maps[GPUEB_MBOX_RECV]);
	snapshot->pending = pending;
	return 0;
}

static irqreturn_t mailbox_irq_thread(int irq, void *data)
{
	struct mt6878_gpueb_reset *scope = data;
	struct gpueb_irq_snapshot snapshot = { .scope = scope };
	unsigned int i;
	int ret;

	(void)irq;
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (ret)
		goto fault;
	/* A queued thread may outlive the mask in drain_irq(). Leave its pending
	 * payload untouched; deliberate quiescence is not a firmware fault.
	 */
	if (scope->dispatch_quiesced) {
		mutex_unlock(&scope->lock);
		return IRQ_HANDLED;
	}
	if (!scope->dispatch_active) {
		/* An unowned external line enable cannot authorize dispatch. Avoid a
		 * level-triggered storm without reading/ACKing firmware state.
		 */
		mask_irq_once(scope);
		mutex_unlock(&scope->lock);
		return IRQ_HANDLED;
	}
	if (scope->reset_written) {
		ret = -ESHUTDOWN;
		goto fault;
	}
	ret = mt6878_gpueb_sram_read_transaction(scope->gpr, scope->mbox,
					       snapshot_mailbox, &snapshot);
	if (ret)
		goto fault;
	mutex_unlock(&scope->lock);
	for (i = 0; i < GPUEB_MBOX_CHANNELS; i++)
		if (snapshot.pending & BIT(i))
			scope->channels[i].receive(scope->channels[i].context, i,
						snapshot.payload[i], gpueb_channels[i].recv_words);
	/* Keep reply channels busy until the client consumes the local response.
	 * drain_irq synchronizes the whole thread, including this retirement.
	 */
	mutex_lock(&scope->lock);
	scope->tx_inflight &= ~snapshot.replies;
	mutex_unlock(&scope->lock);
	return snapshot.pending ? IRQ_HANDLED : IRQ_NONE;
fault:
	contain_irq(scope, ret);
	mutex_unlock(&scope->lock);
	return IRQ_HANDLED;
}

int mt6878_gpueb_reset_bind_channel(struct mt6878_gpueb_reset *scope,
		struct device *client, unsigned int channel,
		mt6878_gpueb_receive_t receive, void *context)
{
	struct module *module;
	int ret = 0;

	if (IS_ERR_OR_NULL(scope) || !client || !receive || channel >= GPUEB_MBOX_CHANNELS ||
	    !client->driver || !client->driver->suppress_bind_attrs)
		return -EINVAL;
	mutex_lock(&scope->lock);
	if (READ_ONCE(scope->first_error)) {
		ret = READ_ONCE(scope->first_error);
		goto out;
	}
	if (scope->dispatch_quiesced || scope->reset_written) {
		ret = -ESHUTDOWN;
		goto out;
	}
	if (scope->registered & BIT(channel)) {
		ret = -EBUSY;
		goto out;
	}
	module = client->driver->owner;
	if (!try_module_get(module)) {
		ret = -ENODEV;
		goto out;
	}
	scope->channels[channel].device = get_device(client);
	scope->channels[channel].module = module;
	scope->channels[channel].driver = client->driver;
	scope->channels[channel].receive = receive;
	scope->channels[channel].context = context;
	scope->registered |= BIT(channel);
out:
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_bind_channel);

struct gpueb_tx {
	struct mt6878_gpueb_reset *scope;
	unsigned int channel;
};

static int tx_before(struct mt6878_gpueb_reader *reader, void *data)
{
	struct gpueb_tx *tx = data;
	struct mt6878_gpueb_reset *scope = tx->scope;
	u32 boot_word;
	int ret;

	ret = mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1);
	if (ret)
		return ret;
	if (boot_word != 0x55667788)
		return -EHOSTDOWN;
	if (readl(scope->mbox_maps[GPUEB_MBOX_SEND]) & BIT(tx->channel))
		return -EBUSY;
	/* Never consume a reply left over from an earlier owner/request. */
	if (gpueb_channels[tx->channel].recv_opt &&
	    (readl(scope->mbox_maps[GPUEB_MBOX_RECV]) & BIT(tx->channel)))
		return -EPROTO;
	return 0;
}

static int tx_commit(struct mt6878_gpueb_reader *reader, void *data)
{
	struct gpueb_tx *tx = data;
	struct mt6878_gpueb_reset *scope = tx->scope;
	u32 boot_word;
	int ret;

	ret = mt6878_gpueb_sram_reader_words(reader, GPUEB_WINDOW_GPR, 0x8, &boot_word, 1);
	if (ret)
		return ret;
	if (boot_word != 0x55667788)
		return -EHOSTDOWN;
	/* ee2 mtk_mbox_send: full SRAM payload, mb(), then SET BIT(pin_index).
	 * Do not require SEND to stay set: remote consumption may be immediate.
	 */
	mb();
	if (gpueb_channels[tx->channel].recv_opt)
		scope->tx_inflight |= BIT(tx->channel);
	writel(BIT(tx->channel), scope->mbox_maps[GPUEB_MBOX_SET]);
	readl(scope->mbox_maps[GPUEB_MBOX_SEND]);
	return 0;
}

int mt6878_gpueb_reset_trysend(struct mt6878_gpueb_reset *scope,
		struct device *client, unsigned int channel,
		const u32 *words, unsigned int count)
{
	struct gpueb_tx tx = { .scope = scope, .channel = channel };
	u32 payload[GPUEB_MBOX_MAX_TX_WORDS];
	struct irq_data *irq_data;
	int ret;

	if (IS_ERR_OR_NULL(scope) || !client || !words || channel >= GPUEB_MBOX_CHANNELS ||
	    count != gpueb_channels[channel].send_words)
		return -EINVAL;
	memcpy(payload, words, count * sizeof(*words));
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (ret)
		goto out;
	if (scope->dispatch_quiesced || scope->reset_written) {
		ret = -ESHUTDOWN;
		goto out;
	}
	if (!(scope->registered & BIT(channel)) || scope->channels[channel].device != client) {
		ret = -ENODEV;
		goto out;
	}
	if (!scope->parent_driver || scope->parent->driver != scope->parent_driver ||
	    !scope->parent_driver->suppress_bind_attrs ||
	    client->driver != scope->channels[channel].driver ||
	    !client->driver->suppress_bind_attrs) {
		ret = -ENODEV;
		goto fault;
	}
	/* Descriptor state alone cannot authorize external/unowned enable_irq.
	 * Both the private owned transition and the real line must be active.
	 */
	irq_data = irq_get_irq_data(scope->irq);
	if (!scope->dispatch_active || !irq_data || irqd_irq_disabled(irq_data) ||
	    scope->irq_contained) {
		ret = -EOPNOTSUPP;
		goto out;
	}
	if (scope->tx_inflight & BIT(channel)) {
		ret = -EBUSY;
		goto out;
	}
	ret = mt6878_gpueb_sram_send_transaction(scope->gpr, scope->mbox,
			channel, payload, count, tx_before, tx_commit, &tx);
	if (!ret || ret == -EBUSY)
		goto out;
fault:
	contain_irq(scope, ret);
	ret = READ_ONCE(scope->first_error);
out:
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_trysend);

struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram)
{
	struct mt6878_gpueb_reset *scope;
	struct resource *resource;
	struct of_phandle_args supplier;
	unsigned int i;
	int ret, irq;

	if (!parent || IS_ERR_OR_NULL(sram) || !parent->dev.pm_domain)
		return ERR_PTR(-EINVAL);
	ret = mt6878_gpueb_sram_check_parent(sram, &parent->dev);
	if (ret)
		return ERR_PTR(ret);
	ret = mt6878_gpueb_reset_validate_resources(parent);
	if (ret)
		return ERR_PTR(ret);
	/* One actual attached MT6878 SPM MFG0 domain, not a caller permission
 * flag or a similarly named arbitrary runtime-PM device.
 */
	if (of_count_phandle_with_args(parent->dev.of_node, "power-domains",
				       "#power-domain-cells") != 1)
		return ERR_PTR(-EINVAL);
	ret = of_parse_phandle_with_args(parent->dev.of_node, "power-domains",
					"#power-domain-cells", 0, &supplier);
	if (ret)
		return ERR_PTR(ret);
	ret = supplier.args_count == 1 &&
		supplier.args[0] == MT6878_POWER_DOMAIN_MFG0_SHUTDOWN &&
		of_device_is_compatible(supplier.np, "mediatek,mt6878-power-controller");
	of_node_put(supplier.np);
	if (!ret)
		return ERR_PTR(-EINVAL);
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_reg_base");
	irq = platform_get_irq_byname(parent, "mbox0");
	if (irq < 0)
		return ERR_PTR(irq);
	if (irq_get_trigger_type(irq) != IRQ_TYPE_LEVEL_HIGH)
		return ERR_PTR(-EINVAL);
	scope = kzalloc(sizeof(*scope), GFP_KERNEL);
	if (!scope)
		return ERR_PTR(-ENOMEM);
	mutex_init(&scope->lock);
	spin_lock_init(&scope->irq_lock);
	scope->sram = sram;
	scope->irq = irq;
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto free;
	}
	/* No fabricated ACTIVE state, attach side effects or resume/power writes.
	 * A later real cold-start owner must produce this existing usage reference.
	 */
	ret = pm_runtime_get_if_in_use(&parent->dev);
	if (ret <= 0) {
		ret = ret ?: -EAGAIN;
		goto put_module;
	}
	scope->parent = get_device(&parent->dev);
	scope->parent_driver = parent->dev.driver;
	scope->gpr = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_GPR);
	if (IS_ERR(scope->gpr)) {
		ret = PTR_ERR(scope->gpr);
		goto put_pm;
	}
	scope->mbox = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_MBOX);
	if (IS_ERR(scope->mbox)) {
		ret = PTR_ERR(scope->mbox);
		goto put_gpr;
	}
	if (!request_mem_region(resource->start, resource_size(resource), dev_name(scope->parent))) {
		ret = -EBUSY;
		goto put_mbox;
	}
	for (i = 0; i < GPUEB_MBOX_CONTROL_COUNT; i++) {
		struct resource *mbox = platform_get_resource_byname(parent, IORESOURCE_MEM,
				gpueb_resources[GPUEB_MBOX_CONTROL_FIRST + i].name);

		if (!request_mem_region(mbox->start, resource_size(mbox), dev_name(scope->parent))) {
			ret = -EBUSY;
			goto release_mbox;
		}
		scope->mbox_control[i] = mbox;
		scope->mbox_claims++;
	}
	for (i = 0; i < GPUEB_MBOX_CONTROL_COUNT; i++) {
		struct resource *mbox = scope->mbox_control[i];

		scope->mbox_maps[i] = ioremap(mbox->start, resource_size(mbox));
		if (!scope->mbox_maps[i]) {
			ret = -ENOMEM;
			goto release_mbox;
		}
	}
	scope->registers = ioremap(resource->start, resource_size(resource));
	if (!scope->registers) {
		ret = -ENOMEM;
		goto release_mbox;
	}
	ret = request_threaded_irq(irq, NULL, mailbox_irq_thread,
			  IRQF_ONESHOT | IRQF_NO_AUTOEN, dev_name(scope->parent), scope);
	if (ret)
		goto unmap;
	return scope;
unmap:
	iounmap(scope->registers);
release_mbox:
	release_mailbox_resources(scope);
	release_mem_region(resource->start, resource_size(resource));
put_mbox:
	mt6878_gpueb_sram_put_window(scope->mbox);
put_gpr:
	mt6878_gpueb_sram_put_window(scope->gpr);
put_pm:
	pm_runtime_put_noidle(scope->parent);
	put_device(scope->parent);
put_module:
	module_put(THIS_MODULE);
free:
	kfree(scope);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_prepare);

int mt6878_gpueb_reset_drain_irq(struct mt6878_gpueb_reset *scope)
{
	int ret;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	mutex_lock(&scope->lock);
	scope->dispatch_quiesced = true;
	scope->dispatch_active = false;
	mask_irq_once(scope);
	mutex_unlock(&scope->lock);
	/* Never wait holding the threaded handler's mutex. NO_AUTOEN still has no
	 * enable API; the future activation owner must close the boot gates first.
	 */
	synchronize_irq(scope->irq);
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (ret)
		mt6878_gpueb_sram_unknown_start(scope->sram);
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_drain_irq);

int mt6878_gpueb_reset_hold(struct mt6878_gpueb_reset *scope)
{
	int ret;
	unsigned long flags;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	ret = mt6878_gpueb_reset_drain_irq(scope);
	if (ret)
		return ret;
	mutex_lock(&scope->lock);
	spin_lock_irqsave(&scope->irq_lock, flags);
	ret = scope->first_error;
	if (ret)
		goto unlock_irq;
	if (scope->reset_written) {
		ret = -EALREADY;
		goto unlock_irq;
	}
	/* Exact B4.1 LK 0x1edf8 reset assertion. Mark uncertain before MMIO:
 * reset readback proves a latch value, never physical OFF or AXI idle.
 */
	scope->reset_written = true;
	writel(0, scope->registers + 0x600);
	if (readl(scope->registers + 0x600)) {
		scope->first_error = -EIO;
		ret = scope->first_error;
	}
unlock_irq:
	spin_unlock_irqrestore(&scope->irq_lock, flags);
	if (ret && ret != -EALREADY)
		mt6878_gpueb_sram_unknown_start(scope->sram);
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_hold);

int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope)
{
	int ret;
	unsigned int i;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	ret = mt6878_gpueb_reset_drain_irq(scope);
	if (ret)
		return ret;
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (scope->reset_written || ret) {
		if (ret)
			mt6878_gpueb_sram_unknown_start(scope->sram);
		mutex_unlock(&scope->lock);
		return ret ?: -EBUSY;
	}
	mutex_unlock(&scope->lock);
	free_irq(scope->irq, scope);
	for (i = 0; i < GPUEB_MBOX_CHANNELS; i++) {
		if (!(scope->registered & BIT(i)))
			continue;
		put_device(scope->channels[i].device);
		module_put(scope->channels[i].module);
	}
	iounmap(scope->registers);
	release_mailbox_resources(scope);
	release_mem_region(0x13c60000, 0x2000);
	mt6878_gpueb_sram_put_window(scope->mbox);
	mt6878_gpueb_sram_put_window(scope->gpr);
	pm_runtime_put_noidle(scope->parent);
	put_device(scope->parent);
	kfree(scope);
	module_put(THIS_MODULE);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_destroy);
MODULE_LICENSE("GPL");
