struct gpueb_primary_install {
	struct mt6878_gpueb_sram *sram;
	struct mt6878_gpueb_reset *reset;
	const unsigned char *primary;
	unsigned int bytes;
};

/* Called only by the real reset owner with its mutex held and IRQ drained.
 * The SRAM object is quarantined BEFORE reset MMIO, including success. This
 * diagnostic cannot transition back to session IO or authorize a later start.
 */
static int install_quarantined_primary(struct mt6878_gpueb_window *gpr,
		struct mt6878_gpueb_window *mbox, void *data)
{
	struct gpueb_primary_install *input = data;
	struct mt6878_gpueb_sram *sram = input->sram;
	unsigned int offset;
	u32 expected;
	int ret = 0;

	if (IS_ERR_OR_NULL(gpr) || IS_ERR_OR_NULL(mbox) ||
	    gpr->sram != sram || mbox->sram != sram ||
	    gpr->type != GPUEB_WINDOW_GPR || mbox->type != GPUEB_WINDOW_MBOX ||
	    !input->primary || input->bytes != 156064)
		return -EINVAL;
	mutex_lock(&sram->lock);
	if (sram->core.phase != GPUEB_SRAM_QUARANTINED ||
	    sram->core.clients != ((1U << GPUEB_WINDOW_GPR) | (1U << GPUEB_WINDOW_MBOX))) {
		ret = -ESHUTDOWN;
		goto out;
	}
	/* LK's full bank initialization is independent of its source overread.
	 * Do not upload padding, a +24 prefix, xfile or the 258744-byte stock span.
	 */
	memset_io(sram->mapping, 0, GPUEB_SRAM_SIZE);
	for (offset = 0; offset < input->bytes; offset += sizeof(u32))
		writel(get_unaligned_le32(input->primary + offset), sram->mapping + offset);
	wmb();
	/* Check the installed signed primary AND explicit zero-initialized bank.
	 * This is a reset-held diagnostic, not BOOTREADY or a DMA-idle proof.
	 */
	for (offset = 0; offset < GPUEB_SRAM_SIZE; offset += sizeof(u32)) {
		expected = offset < input->bytes ? get_unaligned_le32(input->primary + offset) : 0;
		if (readl(sram->mapping + offset) != expected) {
			ret = -EIO;
			break;
		}
	}
out:
	mutex_unlock(&sram->lock);
	return ret;
}

static int install_owned_snapshot(const unsigned char *primary,
		unsigned int bytes, void *data)
{
	struct gpueb_primary_install *input = data;
	int ret;

	if (!primary || bytes != 156064)
		return -ENOEXEC;
	input->primary = primary;
	input->bytes = bytes;
	ret = mt6878_gpueb_reset_primary_transaction(input->reset, input->sram,
						  install_quarantined_primary, input);
	input->primary = NULL;
	return ret;
}

int mt6878_gpueb_sram_install_retained(struct mt6878_gpueb_sram *sram,
		struct mt6878_gpueb_reset *reset, struct platform_device *source)
{
	struct gpueb_primary_install input = { .sram = sram, .reset = reset };

	if (IS_ERR_OR_NULL(sram) || IS_ERR_OR_NULL(reset) || !source)
		return -EINVAL;
	return tetris_gpueb_flat_use_primary(source, install_owned_snapshot, &input);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_install_retained);
