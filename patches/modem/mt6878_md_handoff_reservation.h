/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_MD_HANDOFF_RESERVATION_H
#define MT6878_MD_HANDOFF_RESERVATION_H
#include <linux/soc/mediatek/mt6878_md_startup_scope.h>
struct device_node;
struct mt6878_md_handoff_reservation;

/* Built-in, boot-lifetime metadata owner. Nodes must be two distinct static
 * /reserved-memory children, plain no-map regions. Digest is an UNVERIFIED
 * claim, never read from ROM here. No success AUTH implementation exists.
 * Create before scope_begin; failure leaves *out NULL, success has no teardown
 * API. Neither iomem claims nor DT reservations exclude secure/DMA writers.
 */
int mt6878_md_handoff_reserve(struct device_node *rom, struct device_node *smem,
			    const u8 digest_claim[32],
			    struct mt6878_md_handoff_reservation **out);
extern const struct mt6878_md_handoff_owner mt6878_md_reserved_handoff_ops;
#endif
