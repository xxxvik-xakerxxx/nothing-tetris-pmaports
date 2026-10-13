/* Process context only; the snapshot callback has already admitted profile 1.
 * Reuse the actual sealed dispatch scope, parent/PM pins and disabled IRQ.
 * No independently mapped SRAM, caller reset proof, release or OFF transition.
 */
int mt6878_gpueb_reset_primary_transaction(struct mt6878_gpueb_reset *scope,
		struct mt6878_gpueb_sram *sram,
		int (*install)(struct mt6878_gpueb_window *, struct mt6878_gpueb_window *, void *),
		void *data)
{
	struct irq_data *irq_data;
	int ret, active;

	if (IS_ERR_OR_NULL(scope) || IS_ERR_OR_NULL(sram) || !install)
		return -EINVAL;
	mutex_lock(&scope->lock);
	if (scope->sram != sram || !scope->dispatch_owner)
		ret = -ENODEV;
	else if (scope->reset_written || scope->dispatch_used || scope->dispatch_active)
		ret = -EALREADY;
	else
		ret = READ_ONCE(scope->first_error);
	mutex_unlock(&scope->lock);
	if (ret)
		return ret;
	/* Never wait for the threaded handler with its mutex held. */
	ret = mt6878_gpueb_reset_drain_irq(scope);
	if (ret)
		return ret;
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (ret)
		goto out;
	if (scope->sram != sram || !scope->dispatch_owner ||
	    scope->dispatch_owner->scope != scope ||
	    scope->dispatch_owner->parent != scope->parent) {
		ret = -ENODEV;
		goto out;
	}
	if (scope->reset_written || scope->dispatch_used || scope->dispatch_active) {
		ret = -EALREADY;
		goto out;
	}
	ret = dispatch_identity(scope);
	if (ret)
		goto out;
	ret = mt6878_gpueb_sram_check_parent(sram, scope->parent);
	if (ret)
		goto out;
	irq_data = irq_get_irq_data(scope->irq);
	if (!irq_data || !irqd_irq_disabled(irq_data)) {
		ret = -EBUSY;
		goto out;
	}
	active = pm_runtime_get_if_in_use(scope->parent);
	if (active <= 0) {
		ret = active ?: -EAGAIN;
		goto out;
	}
	/* Quarantine the one SRAM owner before the first possible hardware write.
	 * Its typed leases and the sealed dispatch PM/module pins stay retained.
	 */
	ret = mt6878_gpueb_sram_unknown_start(sram);
	if (ret)
		goto put_pm;
	scope->reset_written = true;
	writel(0, scope->registers + 0x600);
	if (readl(scope->registers + 0x600))
		ret = -EIO;
	else
		ret = install(scope->gpr, scope->mbox, data);
	if (ret)
		ret = latch(scope, ret);
put_pm:
	/* Only the extra temporary reference: prepare + dispatch pins remain. */
	pm_runtime_put_noidle(scope->parent);
out:
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_primary_transaction);
