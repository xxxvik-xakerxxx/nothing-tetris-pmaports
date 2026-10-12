/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in the actual IOMMU provider; MT6878 camera has three commons. */
static struct device_node *camisp_iommu_root(struct device_node *larb)
{
	struct device_node *seen[4], *node, *result = ERR_PTR(-EINVAL);
	unsigned int count = 0, i;

	node = of_parse_phandle(larb, "mediatek,smi", 0);
	while (node) {
		for (i = 0; i < count; i++)
			if (seen[i] == node)
				break;
		if (i < count || count == ARRAY_SIZE(seen)) {
			of_node_put(node);
			result = ERR_PTR(-ELOOP);
			break;
		}
		seen[count++] = node;
		if (!of_device_is_available(node) || of_node_check_flag(node, OF_DYNAMIC) ||
		    !of_device_is_compatible(node, "mediatek,mt6878-smi-common"))
			break;
		if (!of_find_property(node, "mediatek,smi", NULL)) {
			result = of_node_get(node);
			break;
		}
		if (of_count_phandle_with_args(node, "mediatek,smi", NULL) != 1)
			break;
		node = of_parse_phandle(node, "mediatek,smi", 0);
	}
	while (count)
		of_node_put(seen[--count]);
	return result;
}
