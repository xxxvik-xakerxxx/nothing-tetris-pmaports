/* The diagnostic module/snapshot already remain pinned until reboot.
 * Loan only the observed profile's private verified bytes, synchronously.
 * This adds no writable input, firmware importer or physical-address API.
 */
int tetris_gpueb_flat_use_primary(struct platform_device *input,
		int (*consume)(const unsigned char *, unsigned int, void *), void *data);

int tetris_gpueb_flat_use_primary(struct platform_device *input,
		int (*consume)(const unsigned char *, unsigned int, void *), void *data)
{
	struct flat_analysis *analysis;
	int ret;

	if (!input || !consume)
		return -EINVAL;
	device_lock(&input->dev);
	if (input->dev.driver != &flat_driver.driver) {
		ret = -ENODEV;
		goto out;
	}
	analysis = platform_get_drvdata(input);
	if (!analysis || !analysis->snapshot || !analysis->reservation) {
		ret = -EPROBE_DEFER;
		goto out;
	}
	/* Profile 2 has the same length but its startup layout is not inspected.
	 * Profile 1's digest was admitted by the canonical metadata/hash path.
	 */
	if (analysis->metadata.profile_id != 1 || analysis->size != TETRIS_FLAT_BYTES) {
		ret = -ENOEXEC;
		goto out;
	}
	ret = consume(analysis->snapshot, analysis->size, data);
out:
	device_unlock(&input->dev);
	return ret;
}
EXPORT_SYMBOL_GPL(tetris_gpueb_flat_use_primary);
