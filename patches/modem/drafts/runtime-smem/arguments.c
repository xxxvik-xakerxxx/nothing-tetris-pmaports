/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/slab.h>
#include <linux/unaligned.h>
#include "smem.h"
#include "ccci_util_lib_main.h"

struct tetris_smem_args {
	unsigned char chk[512], nc[36 * 40], cache[10 * 40];
};

static int read_argument(const char *name, unsigned char *destination, unsigned int bytes)
{
	int ret = mtk_ccci_find_args_val(name, destination, bytes);

	if (ret < 0)
		return ret;
	return (unsigned int)ret == bytes ? 0 : -EMSGSIZE;
}

int tetris_smem_from_arguments(const struct tetris_metadata_banks *banks,
		struct tetris_smem_owner **output)
{
	struct tetris_smem_args *args;
	struct tetris_smem_input input;
	unsigned char count[4];
	unsigned int nc_count, cache_count;
	int ret;

	if (!banks || !output)
		return -EINVAL;
	/* Sole serialized init caller; existing importer retains immutable values.
	 * No I/O, user pointers, protected ROM or mutable placed-RAM reauthentication.
	 */
	input.banks = *banks;
	ret = read_argument("nc_smem_layout_num", count, sizeof(count));
	if (ret)
		return ret;
	nc_count = get_unaligned_le32(count);
	ret = read_argument("c_smem_layout_num", count, sizeof(count));
	if (ret)
		return ret;
	cache_count = get_unaligned_le32(count);
	if (nc_count < 18 || nc_count > 36 || cache_count < 5 || cache_count > 10)
		return -ERANGE;
	args = kzalloc(sizeof(*args), GFP_KERNEL);
	if (!args)
		return -ENOMEM;
	ret = read_argument("md1_chk", args->chk, sizeof(args->chk));
	if (!ret)
		ret = read_argument("nc_smem_layout", args->nc, nc_count * 40);
	if (!ret)
		ret = read_argument("c_smem_layout", args->cache, cache_count * 40);
	if (!ret) {
		input.chk = args->chk;
		input.chk_bytes = sizeof(args->chk);
		input.nc = args->nc;
		input.nc_bytes = nc_count * 40;
		input.cache = args->cache;
		input.cache_bytes = cache_count * 40;
		ret = tetris_smem_create(&input, output);
	}
	kfree(args);
	return ret;
}
