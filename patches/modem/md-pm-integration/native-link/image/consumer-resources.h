/* SPDX-License-Identifier: GPL-2.0-only */
/* Included before the actual B4.1 md_cd_get_modem_hw_info caller. */
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
#include <linux/io.h>
#include <linux/soc/mediatek/mt6878_md_native_on.h>

static int ccci_tetris_consumer_resources(struct platform_device *pdev,
					struct md_hw_info *hw)
{
	struct resource *sram, *sequencer;
	u32 epon[2];
	int ret;

	ret = mt6878_md_native_on_validate(&pdev->dev);
	if (ret)
		return ret;
	/* This is normal resource acquisition, NOT an NS secure-access grant.
	 * The candidate DT stays disabled until the loader/secure owners exist.
	 */
	sram = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	sequencer = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	if (!sram || !sequencer || platform_get_resource(pdev, IORESOURCE_MEM, 2) ||
	    resource_size(sram) != 0x2000 || resource_size(sequencer) != 0x1000 ||
	    resource_overlaps(sram, sequencer) ||
	    of_property_count_u32_elems(pdev->dev.of_node, "mediatek,offset-epon-md1") != 2)
		return -EINVAL;
	ret = of_property_read_u32_array(pdev->dev.of_node, "mediatek,offset-epon-md1", epon, 2);
	if (ret)
		return ret;
	if (epon[0] != 0x64 || epon[1] != 6)
		return -EXDEV;
	ret = platform_get_irq(pdev, 0);
	if (ret < 0)
		return ret;
	if (!ret)
		return -EINVAL;
	hw->md_wdt_irq_id = ret;
	hw->md_l2sram_base = devm_ioremap_resource(&pdev->dev, sram);
	if (IS_ERR(hw->md_l2sram_base))
		return PTR_ERR(hw->md_l2sram_base);
	hw->sequencer_base = devm_ioremap_resource(&pdev->dev, sequencer);
	if (IS_ERR(hw->sequencer_base))
		return PTR_ERR(hw->sequencer_base);
	hw->md_l2sram_size = resource_size(sram);
	hw->md_epon_offset = epon[0];
	return 0;
}
#endif
