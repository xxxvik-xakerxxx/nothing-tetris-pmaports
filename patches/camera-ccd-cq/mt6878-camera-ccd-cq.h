/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CCD_CQ_H
#define MT6878_CAMERA_CCD_CQ_H

#ifdef __KERNEL__
#include <linux/errno.h>
#include <linux/types.h>
typedef u64 mt6878_cq_u64;
#else
#include <errno.h>
#include <stdint.h>
typedef uint64_t mt6878_cq_u64;
#endif

/* B4.1 libccd.so cq_append_with_values, cq_append_desc_end. This builds
 * memory only. The capture owner must validate the actual register list,
 * resource ownership, mapping lifetime and cache synchronization separately.
 * The encoded register aperture is a hardware CQ format, not an MMIO mapping.
 */
#define MT6878_CQ_REG_BASE 0x1a000000U
#define MT6878_CQ_REG_SIZE 0x00200000U
#define MT6878_CQ_DESC_BYTES 12U
#define MT6878_CQ_MAX_WORDS 511U
#define MT6878_CQ_END 0x06000000U

struct mt6878_ccd_cq {
	unsigned char *buffer;
	mt6878_cq_u64 iova;
	unsigned int capacity, head, tail;
	unsigned int reg_base, reg_size, finished;
	int first_error;
};

static inline void mt6878_cq_put32(unsigned char *p, unsigned int v)
{
	p[0] = v;
	p[1] = v >> 8;
	p[2] = v >> 16;
	p[3] = v >> 24;
}

static inline void mt6878_cq_put64(unsigned char *p, mt6878_cq_u64 v)
{
	mt6878_cq_put32(p, (unsigned int)v);
	mt6878_cq_put32(p + 4, (unsigned int)(v >> 32));
}

static inline int mt6878_cq_fail(struct mt6878_ccd_cq *cq, int error)
{
	if (!cq->first_error)
		cq->first_error = error;
	return cq->first_error;
}

/* reg_base/size must come from an exclusively owned, source-validated CAMSV
 * resource. Accepting this range is not permission to write every register.
 * No initialization while a previous CQ is in flight. Serialized by owner.
 */
static inline int mt6878_ccd_cq_init(struct mt6878_ccd_cq *cq,
	unsigned char *buffer, unsigned int capacity, mt6878_cq_u64 iova,
	unsigned int reg_base, unsigned int reg_size)
{
	if (!cq || !buffer || capacity < 28 || (capacity & 3) || (iova & 15) ||
	    iova >= ((mt6878_cq_u64)1 << 34) ||
	    capacity > ((mt6878_cq_u64)1 << 34) - iova ||
	    reg_base < MT6878_CQ_REG_BASE || (reg_base & 3) ||
	    !reg_size || (reg_size & 3) || reg_size > MT6878_CQ_REG_SIZE ||
	    reg_base - MT6878_CQ_REG_BASE > MT6878_CQ_REG_SIZE - reg_size)
		return -EINVAL;
	cq->buffer = buffer;
	cq->iova = iova;
	cq->capacity = capacity;
	cq->head = 0;
	cq->tail = capacity;
	cq->reg_base = reg_base;
	cq->reg_size = reg_size;
	cq->finished = 0;
	cq->first_error = 0;
	return 0;
}

/* Values are native u32; output is explicitly little-endian. Values must not
 * alias the CQ buffer. Reserve the final END before any mutation, unlike the
 * stock append path which may return ENOMEM after partially writing a frame.
 */
static inline int mt6878_ccd_cq_values(struct mt6878_ccd_cq *cq,
	unsigned int reg, const unsigned int *values, unsigned int count)
{
	unsigned int bytes, descriptors, offset, left, n, j, command;
	unsigned long src, dst;
	mt6878_cq_u64 value_iova;

	if (!cq || !cq->buffer)
		return -EINVAL;
	if (cq->first_error)
		return cq->first_error;
	if (cq->finished)
		return -EALREADY;
	if (!values || !count || (reg & 3) || reg < cq->reg_base ||
	    reg - cq->reg_base >= cq->reg_size ||
	    count > (cq->reg_size - (reg - cq->reg_base)) / 4)
		return mt6878_cq_fail(cq, -ERANGE);
	bytes = count * 4;
	descriptors = (count + MT6878_CQ_MAX_WORDS - 1) / MT6878_CQ_MAX_WORDS;
	if (cq->head > cq->tail || bytes > cq->tail - cq->head ||
	    descriptors * MT6878_CQ_DESC_BYTES + MT6878_CQ_DESC_BYTES >
	    cq->tail - cq->head - bytes ||
	    cq->head + descriptors * MT6878_CQ_DESC_BYTES + MT6878_CQ_DESC_BYTES > 65535)
		return mt6878_cq_fail(cq, -ENOSPC);
	src = (unsigned long)values;
	dst = (unsigned long)cq->buffer;
	if ((src >= dst && src - dst < cq->capacity) ||
	    (src < dst && dst - src < bytes))
		return mt6878_cq_fail(cq, -EINVAL);
	offset = cq->tail - bytes;
	for (j = 0; j < count; j++)
		mt6878_cq_put32(cq->buffer + offset + j * 4, values[j]);
	value_iova = cq->iova + offset;
	left = count;
	while (left) {
		n = left > MT6878_CQ_MAX_WORDS ? MT6878_CQ_MAX_WORDS : left;
		command = (reg & 0xffff) | (((reg >> 16) & 31) << 27) |
			((n - 1) << 16);
		mt6878_cq_put32(cq->buffer + cq->head, command);
		mt6878_cq_put64(cq->buffer + cq->head + 4, value_iova);
		cq->head += MT6878_CQ_DESC_BYTES;
		reg += n * 4;
		value_iova += n * 4;
		left -= n;
	}
	cq->tail = offset;
	return 0;
}

/* camsys_sv_compose 0x33d44..0x33e78 writes the frame cookie to all eight
 * FH_SPARE tags. Pinned mtk_cam-sv-regs.h: offset 0x57c, tag stride 0x40.
 * central_base is the actual owned central resource, not an inferred mapping.
 * This is only one part of the real frame recipe, never a capture-ready CQ.
 */
static inline int mt6878_ccd_cq_frame_cookie(struct mt6878_ccd_cq *cq,
	unsigned int central_base, unsigned int session, unsigned int cookie)
{
	unsigned int reg, last, tag;
	int ret;

	if (!cq || !cq->buffer)
		return -EINVAL;
	if (cq->first_error)
		return cq->first_error;
	if (cq->finished)
		return -EALREADY;
	if (session > 3 || cookie >> 24 != session ||
	    central_base < cq->reg_base || (central_base & 3) ||
	    central_base - cq->reg_base >= cq->reg_size ||
	    cq->reg_size - (central_base - cq->reg_base) < 0x740)
		return mt6878_cq_fail(cq, -ERANGE);
	reg = central_base + 0x57c;
	last = reg + 7 * 0x40;
	if (last < reg || cq->head > cq->tail ||
	    cq->tail - cq->head < 8 * (MT6878_CQ_DESC_BYTES + 4) +
	    MT6878_CQ_DESC_BYTES ||
	    cq->head + 9 * MT6878_CQ_DESC_BYTES > 65535)
		return mt6878_cq_fail(cq, -ENOSPC);
	for (tag = 0; tag < 8; tag++) {
		ret = mt6878_ccd_cq_values(cq, reg + tag * 0x40, &cookie, 1);
		if (ret)
			return ret;
	}
	return 0;
}

/* descriptor_bytes, not capacity or value bytes, is the CQ hardware length.
 * The full buffer including the tail must remain mapped until DMA quiescence.
 */
static inline int mt6878_ccd_cq_finish(struct mt6878_ccd_cq *cq,
	unsigned int *descriptor_bytes, unsigned int *values_start)
{
	if (!cq || !cq->buffer || !descriptor_bytes || !values_start)
		return -EINVAL;
	if (cq->first_error)
		return cq->first_error;
	if (cq->finished)
		return -EALREADY;
	if (!cq->head || cq->head > cq->tail ||
	    cq->tail - cq->head < MT6878_CQ_DESC_BYTES)
		return mt6878_cq_fail(cq, -ENOSPC);
	mt6878_cq_put32(cq->buffer + cq->head, MT6878_CQ_END);
	mt6878_cq_put64(cq->buffer + cq->head + 4, 0);
	cq->head += MT6878_CQ_DESC_BYTES;
	cq->finished = 1;
	*descriptor_bytes = cq->head;
	*values_start = cq->tail;
	return 0;
}

#endif
