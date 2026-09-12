#include <assert.h>
#include <stdbool.h>
#include <stdio.h>

struct list_head { unsigned int packets; };
struct gro_node { unsigned int rx_count; struct list_head rx_list; };
struct napi_struct { struct gro_node gro; };
struct ccmni_instance { struct napi_struct *napi; };
static unsigned int pending, flushes, deliveries, delivered, resets;

static void napi_gro_flush(struct napi_struct *napi, bool old)
{
    assert(!old);
    flushes++;
    napi->gro.rx_count += pending;
    napi->gro.rx_list.packets += pending;
    pending = 0;
}

static void netif_receive_skb_list(struct list_head *list)
{
    assert(flushes > 0);
    assert(list->packets > 0);
    deliveries++;
    delivered += list->packets;
    list->packets = 0;
}

static void init_list_head(struct list_head *list)
{
    assert(deliveries > 0);
    assert(list->packets == 0);
    resets++;
}
#define INIT_LIST_HEAD(list) init_list_head(list)
#include "flush.h"

int main(void)
{
    unsigned int cases = 0;
    for (unsigned int queued = 0; queued < 4; queued++) {
        for (unsigned int aggregation = 0; aggregation < 4; aggregation++) {
            struct napi_struct napi = { .gro = {
                .rx_count = queued, .rx_list = { queued },
            }};
            struct ccmni_instance ccmni = { .napi = &napi };
            pending = aggregation;
            flushes = deliveries = delivered = resets = 0;
            for (unsigned int repeat = 0; repeat < 3; repeat++) {
                napi_gro_list_flush(&ccmni);
                assert(napi.gro.rx_count == 0);
                assert(napi.gro.rx_list.packets == 0);
                assert(delivered == queued + aggregation);
                assert(deliveries == (queued + aggregation != 0));
                assert(resets == deliveries);
                assert(flushes == repeat + 1);
                cases++;
            }
        }
    }
    printf("PASS: %u GRO queue/aggregation/repeat cases\n", cases);
    return 0;
}
