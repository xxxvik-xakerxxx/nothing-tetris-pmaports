/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "hf-abi.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
        struct hf_command cmd = hf_make_command(5, 1);
        int64_t period, latency;
        struct hf_event event = { .timestamp = 100, .sensor = 1 };
        assert(cmd.sensor == 5 && cmd.action == 1 && cmd.length == 16);
        memcpy(&period, cmd.data, 8);
        memcpy(&latency, cmd.data + 8, 8);
        assert(period == 40000000 && latency == 0);
        for (size_t i = 16; i < sizeof(cmd.data); i++) assert(cmd.data[i] == 0);
        cmd = hf_make_command(8, 0);
        assert(cmd.sensor == 8 && cmd.action == 0);
        assert(hf_valid_data(&event, 1, 99));
        assert(!hf_valid_data(&event, 1, 100));
        assert(!hf_valid_data(&event, 1, 101));
        assert(!hf_valid_data(&event, 5, 0));
        event.action = 1;
        assert(!hf_valid_data(&event, 1, 0));
        event.action = 0; event.timestamp = 0;
        assert(!hf_valid_data(&event, 1, -1));
        event.timestamp = -1;
        assert(!hf_valid_data(&event, 1, -2));
        assert(_IOC(_IOC_READ | _IOC_WRITE, 'a', 6, sizeof(struct hf_packet)) == 0xc0446106U);
        puts("HF ABI command, event and ioctl tests passed");
        return 0;
}
