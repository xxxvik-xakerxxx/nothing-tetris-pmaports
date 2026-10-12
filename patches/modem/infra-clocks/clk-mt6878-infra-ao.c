// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2023 MediaTek Inc.
 * Author: Chuan-wen Chen <chuan-wen.chen@mediatek.com>
 */

#include <dt-bindings/clock/mediatek,mt6878-clock.h>
#include <linux/module.h>
#include <linux/of_device.h>
#include <linux/platform_device.h>

#include "clk-gate.h"
#include "clk-mtk.h"

static const struct mtk_gate_regs ifrao0_cg_regs = {
	.set_ofs = 0x80,
	.clr_ofs = 0x84,
	.sta_ofs = 0x90,
};

static const struct mtk_gate_regs ifrao1_cg_regs = {
	.set_ofs = 0x88,
	.clr_ofs = 0x8c,
	.sta_ofs = 0x94,
};

static const struct mtk_gate_regs ifrao2_cg_regs = {
	.set_ofs = 0xa4,
	.clr_ofs = 0xa8,
	.sta_ofs = 0xac,
};

static const struct mtk_gate_regs ifrao3_cg_regs = {
	.set_ofs = 0xc0,
	.clr_ofs = 0xc4,
	.sta_ofs = 0xc8,
};

static const struct mtk_gate_regs ifrao4_cg_regs = {
	.set_ofs = 0xe0,
	.clr_ofs = 0xe4,
	.sta_ofs = 0xe8,
};

#define GATE_IFRAO(_bank, _id, _name, _parent, _shift) \
	GATE_MTK(_id, _name, _parent, &ifrao##_bank##_cg_regs, \
		 _shift, &mtk_clk_gate_ops_setclr)

static const struct mtk_gate ifrao_clks[] = {
	GATE_IFRAO(0, CLK_IFRAO_CQ_DMA_FPC, "ifrao_dma", "f26m_ck", 28),
	GATE_IFRAO(1, CLK_IFRAO_CCIF1_AP, "ifrao_ccif1_ap", "axi_ck", 12),
	GATE_IFRAO(1, CLK_IFRAO_CCIF1_MD, "ifrao_ccif1_md", "axi_ck", 13),
	GATE_IFRAO(1, CLK_IFRAO_CCIF_AP, "ifrao_ccif_ap", "axi_ck", 23),
	GATE_IFRAO(1, CLK_IFRAO_CCIF_MD, "ifrao_ccif_md", "axi_ck", 26),
	GATE_IFRAO(2, CLK_IFRAO_CLDMA_BCLK, "ifrao_cldmabclk", "axi_ck", 3),
	GATE_IFRAO(2, CLK_IFRAO_CQ_DMA, "ifrao_cq_dma", "axi_ck", 27),
	GATE_IFRAO(3, CLK_IFRAO_CCIF5_MD, "ifrao_ccif5_md", "axi_ck", 10),
	GATE_IFRAO(3, CLK_IFRAO_CCIF2_AP, "ifrao_ccif2_ap", "axi_ck", 16),
	GATE_IFRAO(3, CLK_IFRAO_CCIF2_MD, "ifrao_ccif2_md", "axi_ck", 17),
	GATE_IFRAO(3, CLK_IFRAO_DPMAIF_MAIN, "ifrao_dpmaif_main", "dpmaif_main_ck", 26),
	GATE_IFRAO(3, CLK_IFRAO_CCIF4_MD, "ifrao_ccif4_md", "axi_ck", 29),
	GATE_IFRAO(4, CLK_IFRAO_RG_MMW_DPMAIF26M, "ifrao_dpmaif_26m", "f26m_ck", 17),
};

static const struct mtk_clk_desc ifrao_desc = {
	.clks = ifrao_clks,
	.num_clks = ARRAY_SIZE(ifrao_clks),
};

static const struct of_device_id of_match_clk_mt6878_infra_ao[] = {
	{ .compatible = "mediatek,mt6878-infracfg-ao", .data = &ifrao_desc },
	{ }
};
MODULE_DEVICE_TABLE(of, of_match_clk_mt6878_infra_ao);

static struct platform_driver clk_mt6878_infra_ao_driver = {
	.probe = mtk_clk_simple_probe,
	.remove = mtk_clk_simple_remove,
	.driver = {
		.name = "clk-mt6878-infra-ao",
		.of_match_table = of_match_clk_mt6878_infra_ao,
	},
};
module_platform_driver(clk_mt6878_infra_ao_driver);

MODULE_DESCRIPTION("MediaTek MT6878 infrastructure AO clocks");
MODULE_LICENSE("GPL");
