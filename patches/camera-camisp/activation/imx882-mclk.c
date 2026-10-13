/* SPDX-License-Identifier: GPL-2.0-only */
/* Inserted into imx882-identity.c, using its existing resource owner. */

static void imx882_mclk_release(struct imx882_identity *imx882)
{
	if (imx882->rate_exclusive) {
		clk_rate_exclusive_put(imx882->xclk);
		imx882->rate_exclusive = false;
	}
	if (imx882->source_rate_exclusive) {
		clk_rate_exclusive_put(imx882->xclk_source);
		imx882->source_rate_exclusive = false;
	}
}

static int imx882_mclk_acquire(struct imx882_identity *imx882)
{
	int ret;

	if (clk_is_match(imx882->xclk, imx882->xclk_source))
		return -EINVAL;
	ret = clk_rate_exclusive_get(imx882->xclk);
	if (ret)
		return ret;
	imx882->rate_exclusive = true;
	/* Do not reparent an output left running by another owner. */
	if (__clk_is_enabled(imx882->xclk)) {
		ret = -EBUSY;
		goto release;
	}
	ret = clk_rate_exclusive_get(imx882->xclk_source);
	if (ret)
		goto release;
	imx882->source_rate_exclusive = true;
	/* B4.1 uses UVPLL192M_D8. Never tune the shared PLL to obtain 24 MHz. */
	if (clk_get_rate(imx882->xclk_source) != IMX882_XCLK_RATE) {
		ret = -ERANGE;
		goto release;
	}
	ret = clk_set_parent(imx882->xclk, imx882->xclk_source);
	if (ret)
		goto release;
	if (!clk_is_match(clk_get_parent(imx882->xclk), imx882->xclk_source) ||
	    clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE) {
		ret = -EIO;
		goto release;
	}
	return 0;

release:
	imx882_mclk_release(imx882);
	return ret;
}
