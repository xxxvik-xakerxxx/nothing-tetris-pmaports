#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define BIT(n) (UINT32_C(1) << (n))
#define GENMASK(h, l) ((UINT32_MAX >> (31 - (h))) & (UINT32_MAX << (l)))
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))
typedef uint8_t u8;
#include "components.h"
struct mtk_mmsys_routes {
    unsigned int from_comp, to_comp, addr;
    uint32_t mask, val;
};
#define mt6878_mmsys_routing_table baseline_routes
#include "base-route.h"
#undef mt6878_mmsys_routing_table
#undef __SOC_MEDIATEK_MT6878_MMSYS_H
#define mt6878_mmsys_routing_table candidate_routes
#include "candidate-route.h"
#define mt6878_mtk_ddp_main baseline_path
#include "base-path.h"
#undef mt6878_mtk_ddp_main
#define mt6878_mtk_ddp_main candidate_path
#include "candidate-path.h"
#include "mutex.h"

static void connect(uint32_t *regs, const struct mtk_mmsys_routes *routes,
                    size_t nr, const unsigned int *path, size_t np)
{
    for (size_t edge = 1; edge < np; edge++) {
        size_t matches = 0;
        for (size_t i = 0; i < nr; i++) {
            const struct mtk_mmsys_routes *r = &routes[i];
            if (r->from_comp != path[edge - 1] || r->to_comp != path[edge])
                continue;
            assert(r->addr < 0x1000 && r->addr % 4 == 0);
            assert((r->val & ~r->mask) == 0);
            regs[r->addr / 4] = (regs[r->addr / 4] & ~r->mask) | r->val;
            matches++;
        }
        assert(matches != 0);
    }
}

int main(void)
{
    const unsigned int expected[] = {
        DDP_COMPONENT_OVL_2L0, DDP_COMPONENT_OVL_2L1,
        DDP_COMPONENT_OVL_2L2, DDP_COMPONENT_POSTMASK0,
        DDP_COMPONENT_DSC0, DDP_COMPONENT_DSI0,
    };
    assert(sizeof(candidate_path) == sizeof(expected));
    assert(memcmp(candidate_path, expected, sizeof(expected)) == 0);
    assert(mt6878_mutex_mod[DDP_COMPONENT_POSTMASK0] == 14);
    unsigned int before_mask = 0, after_mask = 0;
    for (size_t i = 0; i < COUNT(baseline_path); i++)
        before_mask |= BIT(mt6878_mutex_mod[baseline_path[i]]);
    for (size_t i = 0; i < COUNT(candidate_path); i++)
        after_mask |= BIT(mt6878_mutex_mod[candidate_path[i]]);
    assert(after_mask == (before_mask | BIT(14)));

    for (unsigned int seed = 0; seed < 256; seed++) {
        uint32_t before[1024], after[1024], initial[1024];
        for (size_t i = 0; i < COUNT(initial); i++)
            initial[i] = seed == 0 ? 0 : seed == 1 ? UINT32_MAX :
                         (uint32_t)(i * UINT32_C(2654435761)) ^
                         (seed * UINT32_C(2246822519));
        memcpy(before, initial, sizeof(before));
        memcpy(after, initial, sizeof(after));
        connect(before, baseline_routes, COUNT(baseline_routes),
                baseline_path, COUNT(baseline_path));
        for (unsigned int repeat = 0; repeat < 3; repeat++) {
            connect(after, candidate_routes, COUNT(candidate_routes),
                    candidate_path, COUNT(candidate_path));
            for (size_t i = 0; i < COUNT(after); i++) {
                uint32_t expected_reg = before[i];
                if (i == 0xe24 / 4)
                    expected_reg &= ~BIT(0);
                if (i == 0xd20 / 4)
                    expected_reg |= BIT(1);
                assert(after[i] == expected_reg);
            }
            assert(after[0xd00 / 4] == 0x10001);
            assert(after[0xd30 / 4] == 0);
            assert(after[0xd60 / 4] == 0x20000);
        }
    }
    puts("PASS: 768 route comparisons, component order and POSTMASK mutex bit");
    return 0;
}
