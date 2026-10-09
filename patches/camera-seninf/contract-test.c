/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include "mt6878-seninf-contract.h"

int main(void)
{
	unsigned int lanes[3] = { 0, 1, 2 };
	struct mt6878_seninf_packet packets[2] = {
		{ 0, 0x2b, 15000000 }, { 0, 0x30, 3750000 },
	};
	assert(mt6878_seninf_check_trios(3, lanes) == 0);
	assert(mt6878_seninf_check_trios(2, lanes) == -EINVAL);
	lanes[2] = 1;
	assert(mt6878_seninf_check_trios(3, lanes) == -EINVAL);
	lanes[2] = 3;
	assert(mt6878_seninf_check_trios(3, lanes) == -EINVAL);
	assert(mt6878_seninf_check_packets(4000, 3000, 2, packets) == 0);
	assert(mt6878_seninf_check_packets(4000, 3000, 1, packets) == -EINVAL);
	assert(mt6878_seninf_check_packets(8192, 6144, 2, packets) == -EINVAL);
	packets[1].vc = 1;
	assert(mt6878_seninf_check_packets(4000, 3000, 2, packets) == -EINVAL);
	packets[1].vc = 0;
	packets[1].dt = 0x2b;
	assert(mt6878_seninf_check_packets(4000, 3000, 2, packets) == -EINVAL);
	packets[1].dt = 0x30;
	packets[1].length--;
	assert(mt6878_seninf_check_packets(4000, 3000, 2, packets) == -EINVAL);
	packets[0].length = 11796480;
	packets[1].length = 2949120;
	assert(mt6878_seninf_check_packets(4096, 2304, 2, packets) == 0);
	packets[0].length = 0xffffffffU;
	assert(mt6878_seninf_check_packets(4096, 2304, 2, packets) == -EINVAL);
	puts("SENINF production contract: modes, packets and trio rejection PASS");
	return 0;
}
