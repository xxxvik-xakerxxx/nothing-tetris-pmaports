/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_ROUTE_PROGRAM_H
#define MT6878_SENINF_ROUTE_PROGRAM_H

#include "mt6878-seninf-mux.h"

/* PHY3.1 set_vc/reset_dt_remap/remap_dt/set_cammux_* from modules
 * e96f60dc081ae3525ef43d4bcf0ee5ee97e53835. Restricted VC0 RAW10/PDAF.
 * The caller owns the core/page lock, allocation, stopped sensor and PHY.
 * No allocation, IRQ enable, TSREC setup or DMA quiescence is invented here.
 */
struct mt6878_route_plan {
	struct mt6878_seninf_plan outputs[2];
	unsigned int cammux[2], tags[2], width, height;
};

struct mt6878_route_transaction {
	struct mt6878_seninf_transaction bus;
	struct mt6878_route_plan plan;
	unsigned int attempted, configured, disconnect_attempted, disconnected;
};

/* Shared drop/dynamic switching are intentionally outside this restricted
 * one-frame consumer. Reject inherited active paths before modifying MMIO.
 */
static inline int mt6878_route_preflight(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p)
{
	unsigned int value, i;
	int ret;

	ret = io->read(io->context, MT6878_SENINF_BASE, 0x17f08, &value);
	if (ret || (value & 0x300))
		return ret ? ret : -EBUSY;
	for (i = 0; i < 2; i++) {
		ret = io->read(io->context, MT6878_SENINF_BASE,
			0x17000 + p->cammux[i] * 0x40, &value);
		if (ret || (value & ((1U << 23) | (1U << 24) | 0x80)))
			return ret ? ret : -EBUSY;
	}
	return 0;
}

static inline int mt6878_route_validate(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p)
{
	unsigned int i;
	int ret;

	if (!p || !((p->width == 4000 && p->height == 3000) ||
		    (p->width == 4096 && p->height == 2304)) ||
	    p->outputs[0].port != p->outputs[1].port ||
	    p->outputs[0].intf != p->outputs[1].intf ||
	    p->outputs[0].mux == p->outputs[1].mux ||
	    p->outputs[0].group == p->outputs[1].group ||
	    p->cammux[0] == p->cammux[1] || p->tags[0] == p->tags[1])
		return -EINVAL;
	for (i = 0; i < 2; i++) {
		ret = mt6878_seninf_validate_backend(io, &p->outputs[i]);
		if (ret)
			return ret;
		/* Same CAMSV0/1 assignment used by frozen capture submit. */
		if (p->tags[i] > 7 || p->cammux[i] != (p->cammux[0] / 8) * 8 + p->tags[i] ||
		    p->cammux[i] >= 16 || p->outputs[i].mux > 2)
			return -EINVAL;
	}
	return 0;
}

static inline int mt6878_route_write(const struct mt6878_seninf_backend *io,
	struct mt6878_seninf_transaction *tx, enum mt6878_seninf_region region,
	unsigned int offset, unsigned int value)
{
	unsigned long size = region == MT6878_SENINF_BASE ? io->base_size : io->analog_size;

	if (offset & 3 || size < 4 || offset > size - 4)
		return mt6878_seninf_error(tx, -EINVAL);
	tx->step++;
	return mt6878_seninf_error(tx, io->write(io->context, region, offset, value));
}

static inline int mt6878_route_cammux(const struct mt6878_seninf_backend *io,
	struct mt6878_seninf_transaction *tx, const struct mt6878_route_plan *p,
	unsigned int i)
{
	unsigned int b = 0x17000 + p->cammux[i] * 0x40;
	unsigned int dt = i ? 0x30 : 0x2b, shift = (p->tags[i] % 4) * 8;
	int ret = 0;

#define RUP(off, mask, value) do { \
	if (!ret) \
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE, b + (off), mask, value); \
} while (0)
	RUP(4, 0x1f, 0);
	RUP(4, 0x3f00, dt << 8);
	RUP(4, 0x80, 0x80);
	RUP(4, 0x8000, 0x8000);
	RUP(4, 0x07000000, (p->tags[i] / 4) << 24);
	RUP(0x20, 0x1fU << shift, 0);
	RUP(0x20, 0x80U << shift, 0x80U << shift);
	RUP(0x24, 0x3fU << shift, dt << shift);
	RUP(0x24, 0x80U << shift, 0x80U << shift);
	/* MT6878 SAT mux range 0..2 -> muxvr range 0..23, factor 8.
	 * get_vcinfo_by_sensor assigns both VC0 packets muxvr_offset=0.
	 */
	RUP(0, 0x7f, p->outputs[i].mux * 8);
	RUP(0x14, 0xffff, p->width);
	RUP(0x14, 0xffff0000U, (i ? p->height / 4 : p->height) << 16);
	RUP(0, 0x700, p->outputs[i].pixel_mode << 8);
	RUP(0, 0x80, 0x80);
	if (ret)
		return ret;
	/* Exact vendor CAMMUX status clear, not a guessed CAMSV DONE ACK. */
	ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE, b + 0xc, 0x103);
	RUP(0, 0x7f0000, (p->outputs[i].mux * 8) << 16);
#undef RUP
	return ret;
}

static inline int mt6878_route_setup(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p, struct mt6878_route_transaction *tx)
{
	struct mt6878_seninf_transaction mux = { 0 };
	unsigned int b, mac, i, dt, bits;
	int ret;

	if (!tx || tx->attempted || tx->bus.first_error)
		return -EBUSY;
	ret = mt6878_route_validate(io, p);
	for (i = 0; !ret && i < 2; i++)
		ret = io->check(io->context, MT6878_MUX_SETUP, &p->outputs[i]);
	if (!ret)
		ret = mt6878_route_preflight(io, p);
	if (ret)
		return ret; /* Entire allocation/ownership checked before MMIO. */
	tx->plan = *p;
	tx->attempted = 1;
	b = 0xa00 + p->outputs[0].intf * 0x1000;
	mac = 0x5000 + p->outputs[0].port * 0x8000;
#define UPDATE(region, off, mask, value) do { \
	if (!ret) \
		ret = mt6878_seninf_update(io, &tx->bus, region, off, mask, value); \
} while (0)
#define TETRIS_ROUTE_WRITE(region, off, value) do { \
	if (!ret) \
		ret = mt6878_route_write(io, &tx->bus, region, off, value); \
} while (0)
	for (i = 0; i < 8; i++)
		TETRIS_ROUTE_WRITE(MT6878_SENINF_BASE, b + 0x20 + i * 4, 0);
	for (i = 0; i < 4; i++)
		TETRIS_ROUTE_WRITE(MT6878_SENINF_BASE, b + 0x60 + i * 4, 0);
	/* Preserve the vendor duplicate FORCEDT0 clear (not FORCEDT1). */
	TETRIS_ROUTE_WRITE(MT6878_SENINF_ANALOG, mac + 0x110, 0);
	TETRIS_ROUTE_WRITE(MT6878_SENINF_ANALOG, mac + 0x110, 0);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x104, 0x3f000000, 0x2e000000);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x104, 0x003f0000, 0x002d0000);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x104, 0x00003f00, 0x00002c00);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x104, 0x0000003f, 0x0000002b);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x110, 0x3f, 0x30);
	/* imgsensor-user.h REMAP_NONE=0, REMAP_TO_RAW10=1. */
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x110, 0x700, 0x100);
	UPDATE(MT6878_SENINF_ANALOG, mac + 0x110, 0x1000, 0x1000);
	for (i = 0; i < 2; i++) {
		dt = i ? 0x30 : 0x2b;
		UPDATE(MT6878_SENINF_BASE, b + 0x20 + i * 4, 0x3f0000, dt << 16);
		UPDATE(MT6878_SENINF_BASE, b + 0x20 + i * 4, 0x1f00, 0);
		UPDATE(MT6878_SENINF_BASE, b + 0x20 + i * 4, 0x30, 0x10);
		UPDATE(MT6878_SENINF_BASE, b + 0x20 + i * 4, 1, 1);
		bits = 1U << (8 + i);
		UPDATE(MT6878_SENINF_BASE, b + 0x60, bits, bits);
		if (p->outputs[i].group)
			UPDATE(MT6878_SENINF_BASE, b + 0x60 + p->outputs[i].group * 4,
			       bits, bits);
		if (ret)
			return ret;
		mux = (struct mt6878_seninf_transaction) { 0 };
		ret = mt6878_seninf_mux_setup(io, &p->outputs[i], &mux);
		/* s_stream_mux: outer setup then CMD_SENINF_FINALIZE_CAM_MUX
		 * repeats the actual setup on inner page, including next source.
		 */
		UPDATE(MT6878_SENINF_BASE, 0x17f04, 0x80, 0x80);
		if (!ret)
			ret = mt6878_route_cammux(io, &tx->bus, p, i);
		UPDATE(MT6878_SENINF_BASE, 0x17f04, 0x80, 0);
		if (!ret)
			ret = mt6878_route_cammux(io, &tx->bus, p, i);
		if (ret)
			return mt6878_seninf_error(&tx->bus, ret);
	}
#undef UPDATE
#undef TETRIS_ROUTE_WRITE
	tx->configured = 1;
	return 0;
}

/* Disconnect only, sensor already stopped. Does not retire PHY/DMA/power.
 * No global drop IRQ write: that belongs to the shared IRQ owner, not a route.
 * Core excludes dynamic switching; native owner must drain IRQ separately.
 */
static inline int mt6878_route_disconnect(const struct mt6878_seninf_backend *io,
	struct mt6878_route_transaction *tx)
{
	struct mt6878_seninf_transaction cleanup = { 0 };
	unsigned int i, page, bank, b, bit;
	int ret;

	if (!tx || !tx->attempted || tx->disconnected)
		return -EINVAL;
	if (tx->disconnect_attempted)
		return tx->bus.first_error ? tx->bus.first_error : -EALREADY;
	ret = mt6878_route_validate(io, &tx->plan);
	for (i = 0; !ret && i < 2; i++)
		ret = io->check(io->context, MT6878_MUX_SETUP, &tx->plan.outputs[i]);
	if (ret)
		return ret;
	tx->disconnect_attempted = 1;
#define OFF(off, mask, value) do { \
	if (!ret) \
		ret = mt6878_seninf_update(io, &cleanup, MT6878_SENINF_BASE, off, mask, value); \
} while (0)
	/* Disable both owned register pages, outer then live inner. */
	for (bank = 0; bank < 2; bank++) {
		OFF(0x17f04, 0x80, bank ? 0 : 0x80);
		for (i = 0; i < 2; i++) {
			b = 0x17000 + tx->plan.cammux[i] * 0x40;
			bit = 1U << tx->plan.cammux[i];
			OFF(0x17fc0, bit, 0);
			OFF(b, 0x7f0000, 0x7f0000);
			OFF(b, 0x7f, 0x7f);
			OFF(b, 0x80, 0);
			if (ret)
				goto failed;
			for (page = 0; page < 4; page++) {
				OFF(b + 4, 0x07000000, page << 24);
				if (!ret)
					ret = mt6878_route_write(io, &cleanup,
						MT6878_SENINF_BASE, b + 0x20, 0);
				if (!ret)
					ret = mt6878_route_write(io, &cleanup,
						MT6878_SENINF_BASE, b + 0x24, 0);
				if (ret)
					goto failed;
			}
			ret = mt6878_route_write(io, &cleanup, MT6878_SENINF_BASE, b + 0xc, 0x103);
			if (ret)
				goto failed;
			OFF(0xd00 + tx->plan.outputs[i].mux * 0x1000, 1, 0);
			if (ret)
				goto failed;
		}
	}
#undef OFF
	tx->configured = 0;
	tx->disconnected = 1;
	return 0;
failed:
	return mt6878_seninf_error(&tx->bus, ret);
}

#endif
