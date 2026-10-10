/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_EVENTS_H
#define MT6878_SENINF_EVENTS_H

#include "mt6878-seninf-route-program.h"

/* e96 PHY3.1: get_csi_irq_status, debug_current_status, record_vsync_info.
 * ACKs are source-proven, including CPHY's different clear register.
 * G1 status ACK is NOT proven; record/mask/quarantine, never guess W1C.
 */
struct mt6878_seninf_events {
	unsigned int mac[2], g1[2], cphy, csi, mux[2];
};

/* Shared CAMMUX timestamp/drop services are not owned by this consumer.
 * Reject their actual enabled bits before the first programming write.
 */
static inline int mt6878_seninf_events_preflight(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p)
{
	unsigned int value;
	int ret = mt6878_route_validate(io, p);

	if (!ret)
		ret = io->read(io->context, MT6878_SENINF_BASE, 0x17f08, &value);
	if (ret || (value & 0x333))
		return ret ? ret : -EBUSY;
	ret = io->read(io->context, MT6878_SENINF_BASE, 0x17fc0, &value);
	if (ret || value)
		return ret ? ret : -EBUSY;
	ret = io->read(io->context, MT6878_SENINF_BASE, 0x17fc4, &value);
	if (ret || (value & 0x7ff))
		return ret ? ret : -EBUSY;
	return mt6878_route_preflight(io, p);
}

static inline int mt6878_seninf_mask_events(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p, struct mt6878_seninf_transaction *tx)
{
	unsigned int i, mac;
	int ret = mt6878_route_validate(io, p);

	for (i = 0; !ret && i < 2; i++) {
		mac = 0x5000 + p->outputs[i].port * 0x8000 + i * 0x1000;
		/* Preserve bit31 IRQ_CLR_MODE and reserved bit15. */
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_ANALOG,
			mac + 0xc0, 0x7fff7fff, 0);
		if (!ret)
			ret = mt6878_seninf_update(io, tx, MT6878_SENINF_ANALOG,
				mac + 0xb8, 0xff, 0);
		if (!ret)
			ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE,
				0xd10 + p->outputs[i].mux * 0x1000, 0xf, 0);
	}
	if (!ret)
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_ANALOG,
			0x30f0 + p->outputs[0].port * 0x8000, 0xf, 0);
	if (!ret)
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE,
			0xac0 + p->outputs[0].intf * 0x1000, 1U << 28, 0);
	return ret;
}

static inline int mt6878_seninf_sample_events(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p, struct mt6878_seninf_events *s)
{
	unsigned int i, mac;
	int ret = mt6878_route_validate(io, p);

	if (!s)
		return -EINVAL;
	for (i = 0; !ret && i < 2; i++) {
		mac = 0x5000 + p->outputs[i].port * 0x8000 + i * 0x1000;
		ret = io->read(io->context, MT6878_SENINF_ANALOG, mac + 0xc8, &s->mac[i]);
		if (!ret)
			ret = io->read(io->context, MT6878_SENINF_ANALOG, mac + 0xbc, &s->g1[i]);
		if (!ret)
			ret = io->read(io->context, MT6878_SENINF_BASE,
				0xd18 + p->outputs[i].mux * 0x1000, &s->mux[i]);
	}
	if (!ret)
		ret = io->read(io->context, MT6878_SENINF_ANALOG,
			0x30f4 + p->outputs[0].port * 0x8000, &s->cphy);
	if (!ret)
		ret = io->read(io->context, MT6878_SENINF_BASE,
			0xac8 + p->outputs[0].intf * 0x1000, &s->csi);
	return ret;
}

static inline int mt6878_seninf_ack_events(const struct mt6878_seninf_backend *io,
	const struct mt6878_route_plan *p, struct mt6878_seninf_transaction *tx,
	const struct mt6878_seninf_events *s)
{
	unsigned int i, mac;
	int ret = mt6878_route_validate(io, p);

	if (!s)
		return -EINVAL;
	for (i = 0; !ret && i < 2; i++) {
		mac = 0x5000 + p->outputs[i].port * 0x8000 + i * 0x1000;
		if (s->mac[i])
			ret = mt6878_route_write(io, tx, MT6878_SENINF_ANALOG,
				mac + 0xc8, 0xffffffffU);
		if (!ret && (s->mux[i] & 3))
			ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE,
				0xd18 + p->outputs[i].mux * 0x1000, 0x103);
	}
	if (!ret && s->csi)
		ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE,
			0xac8 + p->outputs[0].intf * 0x1000, 0xffffffffU);
	if (!ret && (s->cphy & 0xff0000))
		ret = mt6878_route_write(io, tx, MT6878_SENINF_ANALOG,
			0x30f4 + p->outputs[0].port * 0x8000, 0xff0000);
	return ret;
}

/* Exclusive TSREC owner, restricted first frame does not use timestamps.
 * Vendor tsrec_n_settings_clear: stop engine, interrupt disable, VC/DT clear.
 * Base-relative 0x16000 from tsrec_regs_iomem_init, never a physical address.
 */
static inline int mt6878_seninf_tsrec_disable(const struct mt6878_seninf_backend *io,
	struct mt6878_seninf_transaction *tx)
{
	unsigned int n, exp, shift, value;
	int ret = 0;

	if (!io || !io->read || !io->write || io->base_size < 0x18000 || !tx)
		return -EINVAL;
	for (n = 0; !ret && n < 6; n++) {
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE, 0x16000, 1U << n, 0);
		if (!ret)
			ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE,
				0x16010, 0x80000000U, 0); /* Read-clear mode, exact source. */
		shift = (n < 4 ? n : n - 4) * 3;
		if (!ret)
			ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE,
				n < 4 ? 0x16010 : 0x1601c, 7U << shift, 0);
		if (!ret)
			ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE,
				n < 4 ? 0x16010 : 0x1601c, 7U << (shift + 16), 0);
		for (exp = 0; !ret && exp < 3; exp++)
			ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE,
				0x16050 + n * 0x180 + exp * 4, 0);
	}
	/* Ordered MMIO readback, not a guessed hardware ready poll. */
	if (!ret) {
		ret = io->read(io->context, MT6878_SENINF_BASE, 0x16000, &value);
		if (!ret && (value & 0x3f))
			ret = -EIO;
	}
	if (!ret) {
		ret = io->read(io->context, MT6878_SENINF_BASE, 0x16010, &value);
		if (!ret && (value & 0x8fff0fffU))
			ret = -EIO;
	}
	if (!ret) {
		ret = io->read(io->context, MT6878_SENINF_BASE, 0x1601c, &value);
		if (!ret && (value & 0x003f003f))
			ret = -EIO;
	}
	if (ret && !tx->first_error)
		tx->first_error = ret;
	return ret;
}

#endif
