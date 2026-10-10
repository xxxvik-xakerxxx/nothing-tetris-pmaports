/* SPDX-License-Identifier: GPL-2.0+ */
/* Exact extracted producer C with mock query/block I/O and real OpenSSL SHA. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <openssl/evp.h>
#include "protocol.inc"

typedef unsigned char u8;
typedef unsigned int u32;
enum { UCLASS_SCSI = 1, UCLASS_UFS = 2 };
struct ufs_hba {
	struct ufs_desc_size desc_size;
};
struct udevice { struct udevice *parent; int cls, index; void *priv; };
struct blk_desc {
	struct udevice *bdev;
	int uclass_id, target;
	unsigned int lun, blksz;
	unsigned long long lba;
};
typedef struct { size_t bytes; } sha256_context;
static EVP_MD_CTX *hash;
static struct ufs_hba hba;
static struct udevice ufs, scsi, devices[3];
static struct blk_desc blocks[3];
static unsigned char *image;
static size_t image_bytes, hashed;
static int which, attr_calls, desc_calls, reads;

static int device_get_uclass_id(struct udevice *dev) { return dev->cls; }
static void *dev_get_uclass_priv(struct udevice *dev) { return dev->priv; }
static int ufshcd_query_attr(struct ufs_hba *host, enum query_opcode opcode,
		enum attr_idn idn, u8 index, u8 selector, u32 *out)
{
	assert(host == &hba && opcode == UPIU_QUERY_OPCODE_READ_ATTR);
	assert(idn == QUERY_ATTR_IDN_BOOT_LU_EN && !index && !selector);
	attr_calls++;
	if (which == 1)
		return -EIO;
	*out = which == 11 ? 0 : 1;
	return 0;
}
static int __ufshcd_query_descriptor(struct ufs_hba *host, enum query_opcode opcode,
		enum desc_idn idn, u8 index, u8 selector, u8 *out, int *length)
{
	assert(host == &hba && opcode == UPIU_QUERY_OPCODE_READ_DESC);
	assert(idn == QUERY_DESC_IDN_UNIT && index < 3 && !selector);
	assert(*length >= 5 && *length <= 255);
	desc_calls++;
	if (which == 10)
		return -EACCES;
	memset(out, 0, (size_t)*length);
	out[0] = (u8)*length;
	out[1] = QUERY_DESC_IDN_UNIT;
	out[2] = index;
	out[3] = 1;
	out[4] = index ? 1 : 0; /* foreign target also looks boot-selected, must be skipped */
	if (which == 4)
		*length = 4;
	if (which == 5)
		out[0] = 4;
	if (which == 6)
		out[1] = 0xff;
	if (which == 7)
		out[2] = 0xff;
	if (which == 8)
		out[3] = 0;
	if (which == 9)
		out[4] = 3;
	if (which == 12)
		out[4] = 1;
	if (which == 13)
		out[4] = 0;
	return 0;
}
#include "ufs_identity.inc"

static int blk_first_device(int cls, struct udevice **out)
{
	assert(cls == UCLASS_SCSI);
	if (which == 15)
		return -ENODEV;
	*out = devices;
	return 0;
}
static int blk_next_device(struct udevice **out)
{
	if ((*out)->index == 2)
		return which == 14 ? -EIO : -ENODEV;
	*out = devices + (*out)->index + 1;
	return 0;
}
static struct blk_desc *blk_get_by_device(struct udevice *dev)
{
	return which == 16 ? NULL : blocks + dev->index;
}
static void *memalign(size_t alignment, size_t size)
{
	assert(alignment == 64 && size == 4096);
	return which == 35 ? NULL : aligned_alloc(alignment, size);
}
static unsigned long long blk_dread(struct blk_desc *dev, unsigned long long block,
		unsigned long long count, void *out)
{
	assert(dev == blocks + 1 && count && block < dev->lba && count <= dev->lba - block);
	assert(block <= SIZE_MAX / dev->blksz && count <= SIZE_MAX / dev->blksz);
	assert((block + count) * dev->blksz <= image_bytes);
	reads++;
	if ((which == 26 && reads == 1) || (which == 27 && reads == 2) ||
	    (which == 28 && reads == 3))
		return count - 1;
	memcpy(out, image + block * dev->blksz, (size_t)count * dev->blksz);
	return count;
}
static void sha256_starts(sha256_context *ctx)
{
	ctx->bytes = 0;
	assert(EVP_DigestInit_ex(hash, EVP_sha256(), NULL) == 1);
}
static void sha256_update(sha256_context *ctx, const unsigned char *p, unsigned int n)
{
	assert(EVP_DigestUpdate(hash, p, n) == 1);
	ctx->bytes += n;
	hashed += n;
}
static void sha256_finish(sha256_context *ctx, unsigned char out[32])
{
	unsigned int n;
	assert(ctx->bytes == hashed && EVP_DigestFinal_ex(hash, out, &n) == 1 && n == 32);
}
#define ARCH_DMA_MINALIGN 64
#include "policy_identity.inc"

static void put32(unsigned char *p, unsigned int n)
{
	for (unsigned int i = 0; i < 4; i++)
		p[i] = (unsigned char)(n >> (i * 8));
}

int main(int argc, char **argv)
{
	struct blk_desc *selected = (void *)(uintptr_t)1;
	unsigned char measured[32], expected[32];
	unsigned int size = 5187, length, enabled = 0xa5, unit = 0xa5;
	int ret, wanted;
	assert(argc == 2 || argc == 3);
	which = atoi(argv[1]);
	assert(which >= 0 && which < 36);
	ufs = (struct udevice){ .cls = UCLASS_UFS, .priv = &hba };
	scsi = (struct udevice){ .cls = UCLASS_SCSI, .parent = &ufs };
	hba.desc_size.unit_desc = which == 2 ? 4 : which == 3 ? 256 : 45;
	for (int i = 0; i < 3; i++) {
		devices[i] = (struct udevice){ .parent = &scsi, .index = i };
		blocks[i] = (struct blk_desc){ .bdev = devices + i, .uclass_id = UCLASS_SCSI,
			.target = i == 2 ? 1 : 0, .lun = (unsigned int)i, .blksz = 512 };
	}
	if (which == 17)
		blocks[0].uclass_id = UCLASS_UFS;
	if (which == 31)
		ufs.cls = UCLASS_SCSI;
	if (which == 34)
		ufs.priv = NULL;
	/* Direct provider outputs are unchanged on query/protocol failure. */
	if ((which >= 1 && which <= 11) || which == 31 || which == 34) {
		ret = ufs_read_lun_boot_identity(&scsi, 1, &enabled, &unit);
		wanted = which == 1 ? -EIO : which == 10 ? -EACCES :
			which == 11 ? -EPROTONOSUPPORT : which >= 31 ? -EINVAL : -EPROTO;
		assert(ret == wanted && enabled == 0xa5 && unit == 0xa5);
		assert(attr_calls <= 1 && desc_calls <= 1); /* no query retry */
		attr_calls = desc_calls = 0;
		ret = selected_boot(blocks, &selected);
		assert(ret == wanted && selected == (void *)(uintptr_t)1 && !reads);
		assert(attr_calls <= 1 && desc_calls <= 1); /* caller preserves first provider fault */
		return 0;
	}
	ret = selected_boot(blocks, &selected);
	if (which >= 12 && which <= 17) {
		wanted = which == 12 ? -EEXIST : which == 13 || which == 15 ? -ENODEV :
			which == 14 ? -EIO : which == 16 ? -EPROTO : -EINVAL;
		assert(ret == wanted && selected == (void *)(uintptr_t)1 && !reads);
		return 0;
	}
	assert(!ret && selected == blocks + 1 && attr_calls == 2 && desc_calls == 2);
	if (which == 23)
		size = 4U * 1024 * 1024;
	image_bytes = ((size_t)size + 4096 + 4095) & ~4095UL;
	image = calloc(1, image_bytes);
	assert(image);
	memcpy(image, "UFS_BOOT\0", 9);
	memcpy(image + 4096, "MMM\x01", 4);
	put32(image + 4096 + 0x1c, 0x02000f00U);
	put32(image + 4096 + 0x20, size);
	if (which == 32) {
		FILE *file;
		long n;
		assert(argc == 3);
		file = fopen(argv[2], "rb");
		assert(file && !fseek(file, 0, SEEK_END));
		n = ftell(file);
		assert(n >= 0x38 && n <= 4 * 1024 * 1024 && !fseek(file, 0, SEEK_SET));
		free(image);
		image_bytes = ((size_t)n + 4096 + 4095) & ~4095UL;
		image = calloc(1, image_bytes);
		assert(image && fread(image + 4096, 1, (size_t)n, file) == (size_t)n);
		fclose(file);
		memcpy(image, "UFS_BOOT\0", 9);
		size = word(image + 4096 + 0x20);
		assert(size == (unsigned int)n);
	}
	if (which == 33)
		selected->blksz = 4096;
	selected->lba = image_bytes / selected->blksz;
	if (which == 18)
		image[0] ^= 1;
	if (which == 19)
		image[4096] ^= 1;
	if (which == 20)
		put32(image + 4096 + 0x1c, 0);
	if (which == 21)
		put32(image + 4096 + 0x20, 0x37);
	if (which == 22)
		put32(image + 4096 + 0x20, 4U * 1024 * 1024 + 1);
	if (which == 24)
		selected->lba = 1;
	if (which == 25)
		selected->lba = 9;
	if (which == 29)
		image[4096 + 0x40] ^= 1;
	hash = EVP_MD_CTX_new();
	assert(hash);
	memset(measured, 0xa5, sizeof(measured));
	ret = preloader_digest(selected, measured);
	wanted = which == 32 ? 0 : which == 24 ? -EINVAL : which == 35 ? -ENOMEM :
		which >= 26 && which <= 28 ? -EIO :
		which == 21 || which == 22 || which == 25 ? -ERANGE :
		which >= 18 && which <= 20 ? -EBADMSG : -EKEYREJECTED;
	assert(ret == wanted);
	if (!ret || ret == -EKEYREJECTED) {
		assert(hashed == size);
		assert(EVP_Digest(image + 4096, size, expected, &length, EVP_sha256(), NULL) == 1);
		assert(length == 32 && !memcmp(measured, expected, 32));
	} else if (which != 28) {
		assert(!hashed);
	}
	EVP_MD_CTX_free(hash);
	free(image);
	return 0;
}
