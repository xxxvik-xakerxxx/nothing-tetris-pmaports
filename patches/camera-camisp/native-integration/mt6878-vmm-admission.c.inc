/* SPDX-License-Identifier: GPL-2.0-only */
static int scpsys_vmm_admit_legacy_node(struct device *dev, struct device_node *node)
{
	/* B4.1 firmware voters need no regulator handle or *-supply property. */
	if (!of_device_is_compatible(node, "mediatek,vmm_notifier") &&
	    !of_device_is_compatible(node, "mediatek,mtk-mmdvfs-v3"))
		return 0;

	dev_err(dev, "%pOF: legacy VMM firmware voter blocks native supplier admission\n",
		node);
	return -EBUSY;
}
