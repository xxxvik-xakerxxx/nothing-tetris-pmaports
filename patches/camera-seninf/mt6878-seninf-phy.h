/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_PHY_H
#define MT6878_SENINF_PHY_H

#include "mt6878-seninf-mux.h"

/* No live MMIO adapter. Register programs are generated from PHY3.1 in
 * modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835. Clock choices/layout
 * are checked against device ee2be53cb75670b548948636a0db1d1ff112bf12.
 * Only audited IMX882 preview/capture/video, full ports 0/1, identity trio
 * mapping, non-legacy/no-LRTE/no-ULPS are supported. No DMA is configured.
 */
enum mt6878_phy_owner {
	MT6878_PHY_POWER, /* Sensor stopped; CAM_MAIN/CSI_RX, clock/VCORE held under core lock. */
	MT6878_PHY_IRQ,   /* Handler installed; MAC A/B and PHY pending bits owned. */
	MT6878_PHY_ROUTE, /* Allocated SENINF VC/DT destinations; no stream yet. */
	MT6878_PHY_TSREC, /* Separate TSREC owner has configured or disabled routes. */
	MT6878_PHY_QUIESCED /* Sensor, CAMMUX/DMA stopped; IRQ masked/synchronized. */
};

struct mt6878_phy_inputs {
	unsigned int rg_csi; /* Decoded per-port nvmem word, never a default. */
	/* Successful read/decoding of the matched rg_csi cell, not word != 0.
	 * Vendor treats zero as missing, but does not establish hardware-invalid
	 * calibration codes. Provenance and the numeric payload are independent.
	 */
	unsigned int rg_csi_verified, rg_csi_port;
	unsigned int csi_clock_hz; /* Actual held clock, not requested/default rate. */
	unsigned int mipi_pixel_rate;
	unsigned int dphy_trail_ns;
	unsigned int cphy_settle_ns, not_fixed_trail_settle;
	unsigned int lanes[3];
	unsigned int mode; /* 0: 4000x3000 preview/capture, 1: 4096x2304 video. */
	unsigned int legacy_phy, lrte, ulps;
};

struct mt6878_phy_backend {
	struct mt6878_seninf_backend io;
	/* Each owner must verify its resources independently, including the
	 * exact per-device rg_csi provenance and per-module CSI parameters.
	 * IRQ verification precedes any write, since vendor enables IRQ early.
	 * IRQ must cover both MAC halves and PHY; ROUTE must validate this exact
	 * VC/DT/mux/pixel plan; TSREC must prove its separate route ownership.
	 * Unsupported paths return -EOPNOTSUPP here, before the first MMIO.
	 * Checks must be bounded and must not access receiver MMIO or change
	 * suppliers/rates/regulators. No successful placeholder is valid live.
	 */
	int (*verify)(void *context, enum mt6878_phy_owner owner,
		      const struct mt6878_seninf_plan *plan,
		      const struct mt6878_phy_inputs *inputs);
};

struct mt6878_phy_transaction {
	struct mt6878_seninf_transaction bus;
	struct mt6878_phy_inputs inputs;
	unsigned int attempted, configured, off_attempted;
};

enum mt6878_phy_value {
	MT6878_PHY_LITERAL, MT6878_PHY_WRITE, MT6878_PHY_EFUSE,
	MT6878_PHY_SETTLE, MT6878_PHY_TRAIL
};

struct mt6878_phy_op {
	enum mt6878_seninf_region region;
	unsigned int offset, mask, shift;
	enum mt6878_phy_value kind;
	unsigned int value;
};

#include "mt6878-seninf-phy-data.h"

static inline int mt6878_phy_validate(const struct mt6878_phy_backend *backend,
	const struct mt6878_seninf_plan *plan, const struct mt6878_phy_inputs *in)
{
	int ret;

	if (!backend || !backend->verify || !in)
		return -EINVAL;
	ret = mt6878_seninf_validate_backend(&backend->io, plan);
	if (ret)
		return ret;
	if (in->rg_csi_verified != 1 || in->rg_csi_port != plan->port ||
	    in->mipi_pixel_rate != 700800000 ||
	    in->lanes[0] != 0 || in->lanes[1] != 1 || in->lanes[2] != 2 ||
	    in->mode > 1 || in->dphy_trail_ns != (in->mode ? 0x31U : 0x47U) ||
	    in->cphy_settle_ns || in->not_fixed_trail_settle ||
	    in->legacy_phy || in->lrte || in->ulps)
		return -EINVAL;
	if (in->csi_clock_hz != 312000000 && in->csi_clock_hz != 343000000 &&
	    in->csi_clock_hz != 416000000 && in->csi_clock_hz != 499000000)
		return -EINVAL;
	return 0;
}

static inline unsigned int mt6878_phy_settle(unsigned int clock)
{
	/* Vendor settle_formula: ceil(70ns * held CSI clock) - 6. */
	return (unsigned int)((70ULL * clock + 999999999ULL) / 1000000000ULL) - 6;
}

static inline unsigned int mt6878_phy_trail(const struct mt6878_phy_inputs *in)
{
	/* Vendor DPHY_TRAIL_SPEC=224, data_rate=700800000*10/3.
	 * This common register bank is used by CPHY too; trail enable remains 0.
	 */
	unsigned int ui = 224000 / ((in->mipi_pixel_rate * 10ULL / 3) / 1000000);

	if (!in->dphy_trail_ns || in->dphy_trail_ns > ui)
		return 0;
	return (unsigned int)(((ui - in->dphy_trail_ns) *
		(unsigned long long)in->csi_clock_hz + 999999999ULL) / 1000000000ULL);
}

static inline int mt6878_phy_program(const struct mt6878_phy_backend *backend,
	struct mt6878_phy_transaction *tx, const struct mt6878_phy_op *ops,
	unsigned int count, unsigned int half)
{
	const struct mt6878_seninf_backend *io = &backend->io;
	const struct mt6878_seninf_plan *plan = &tx->bus.plan;
	unsigned int i, value, offset;
	int ret;

	for (i = 0; i < count; i++) {
		offset = ops[i].offset + half;
		offset += ops[i].region == MT6878_SENINF_BASE ?
			plan->intf * 0x1000 : plan->port * 0x8000;
		value = ops[i].value;
		if (ops[i].kind == MT6878_PHY_EFUSE)
			value = (tx->inputs.rg_csi >> value) & 0x1f;
		else if (ops[i].kind == MT6878_PHY_SETTLE)
			value = mt6878_phy_settle(tx->inputs.csi_clock_hz);
		else if (ops[i].kind == MT6878_PHY_TRAIL)
			value = mt6878_phy_trail(&tx->inputs);
		if (ops[i].kind == MT6878_PHY_WRITE) {
			unsigned long size = ops[i].region == MT6878_SENINF_BASE ?
				io->base_size : io->analog_size;

			if ((offset & 3) || size < 4 || offset > size - 4)
				return mt6878_seninf_error(&tx->bus, -EINVAL);
			tx->bus.step++;
			ret = io->write(io->context, ops[i].region, offset, value);
		} else {
			if (value > (ops[i].mask >> ops[i].shift))
				return mt6878_seninf_error(&tx->bus, -ERANGE);
			ret = mt6878_seninf_update(io, &tx->bus, ops[i].region,
				offset, ops[i].mask, value << ops[i].shift);
		}
		if (ret)
			return mt6878_seninf_error(&tx->bus, ret);
	}
	return 0;
}

#define MT6878_PHY_PROGRAM(name, half) do { \
	ret = mt6878_phy_program(backend, tx, mt6878_phy_##name, \
		sizeof(mt6878_phy_##name) / sizeof(mt6878_phy_##name[0]), half); \
	if (ret) \
		return ret; \
} while (0)

static inline int mt6878_phy_setup(const struct mt6878_phy_backend *backend,
	struct mt6878_phy_transaction *tx, const struct mt6878_seninf_plan *plan,
	const struct mt6878_phy_inputs *inputs)
{
	unsigned int owner, bit;
	int ret;

	if (!tx)
		return -EINVAL;
	if (tx->bus.first_error)
		return tx->bus.first_error;
	if (tx->attempted || tx->off_attempted || tx->bus.plan_bound)
		return -EALREADY;
	ret = mt6878_phy_validate(backend, plan, inputs);
	if (ret)
		return mt6878_seninf_error(&tx->bus, ret);
	tx->attempted = 1;
	mt6878_seninf_bind_plan(&tx->bus, plan);
	tx->inputs = *inputs;
	for (owner = MT6878_PHY_POWER; owner <= MT6878_PHY_TSREC; owner++) {
		ret = backend->verify(backend->io.context, owner, plan, inputs);
		if (ret)
			return mt6878_seninf_error(&tx->bus, ret);
	}
	/* Preserve mtk_cam_seninf_set_csi_mipi's order, not an inferred order. */
	MT6878_PHY_PROGRAM(init, 0);
	MT6878_PHY_PROGRAM(init, 0x1000);
	MT6878_PHY_PROGRAM(efuse, 0);
	MT6878_PHY_PROGRAM(timing, 0);
	MT6878_PHY_PROGRAM(post, 0);
	MT6878_PHY_PROGRAM(mac_top, 0);
	MT6878_PHY_PROGRAM(mac_fixed, 0);
	MT6878_PHY_PROGRAM(mac, 0);
	MT6878_PHY_PROGRAM(lrte_off, 0);
	bit = 1U << plan->port;
	ret = mt6878_seninf_update(&backend->io, &tx->bus, MT6878_SENINF_BASE,
		MT6878_PHY_TOP_CTRL2, bit, bit);
	if (ret)
		return ret;
	MT6878_PHY_PROGRAM(seninf, 0);
	MT6878_PHY_PROGRAM(analog_setup, 0);
	tx->bus.analog_attempted = 1;
	ret = mt6878_seninf_analog_half(&backend->io, &tx->bus, plan->port * 0x8000, 1);
	if (!ret)
		ret = mt6878_seninf_analog_half(&backend->io, &tx->bus,
			plan->port * 0x8000 + 0x1000, 1);
	if (ret)
		return ret;
	MT6878_PHY_PROGRAM(trios, 0);
	tx->configured = 1;
	return 0; /* Configured receiver only: not a capture completion. */
}

#undef MT6878_PHY_PROGRAM

static inline int mt6878_phy_off(const struct mt6878_phy_backend *backend,
	struct mt6878_phy_transaction *tx)
{
	int ret;

	if (!backend || !tx || !tx->attempted || !tx->bus.plan_bound)
		return -EINVAL;
	if (tx->off_attempted)
		return tx->bus.first_error ? tx->bus.first_error : -EALREADY;
	ret = mt6878_phy_validate(backend, &tx->bus.plan, &tx->inputs);
	if (ret)
		return ret;
	tx->off_attempted = 1;
	ret = backend->verify(backend->io.context, MT6878_PHY_QUIESCED,
		&tx->bus.plan, &tx->inputs);
	if (ret) {
		mt6878_seninf_error(&tx->bus, ret);
		return tx->bus.first_error;
	}
	ret = mt6878_seninf_receiver_off(&backend->io, &tx->bus.plan, &tx->bus);
	tx->configured = 0;
	return tx->bus.first_error ? tx->bus.first_error : ret;
}

#endif
