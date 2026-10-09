/* CI fixture contains the actual patched helper, not a second implementation. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

enum gps_dl_link_id_enum { GPS_DATA_LINK_ID0, GPS_DATA_LINK_ID1 };
static unsigned int warnings, selections, gpio_requests;
static void *g_gps_dl_pinctrl_ptr;
static void *g_gps_dl_pinctrl_state_struct_list[6];
#define GDL_VOIDF() ((void)0)
#define ASSERT_LINK_ID(id, value) do { if ((id) != 0 && (id) != 1) return value; } while (0)
#define pr_warn_once(...) do { ++warnings; } while (0)
#define pinctrl_select_state(...) (++selections)
#define gpio_request(...) (++gpio_requests)
#include "lna-control-under-test.inc"

int main(void)
{
    unsigned int lifecycle, state, link, on, force, i;
    /* NULL, populated, stale/error pointers across remove/reprobe lifecycles. */
    const uintptr_t pointers[] = {0, 1, UINTPTR_MAX};
    for (lifecycle = 0; lifecycle < 4; ++lifecycle) {
        for (state = 0; state < 3; ++state) {
            g_gps_dl_pinctrl_ptr = (void *)pointers[state];
            for (i = 0; i < 6; ++i)
                g_gps_dl_pinctrl_state_struct_list[i] = (void *)pointers[state];
            for (link = 0; link < 2; ++link)
                for (on = 0; on < 2; ++on)
                    for (force = 0; force < 2; ++force)
                        gps_dl_lna_pin_ctrl((enum gps_dl_link_id_enum)link, on, force);
            assert(g_gps_dl_pinctrl_ptr == (void *)pointers[state]);
            for (i = 0; i < 6; ++i)
                assert(g_gps_dl_pinctrl_state_struct_list[i] == (void *)pointers[state]);
        }
    }
    assert(warnings == 96); /* fixture counts attempts; kernel warning is once */
    gps_dl_lna_pin_ctrl((enum gps_dl_link_id_enum)-1, true, true);
    gps_dl_lna_pin_ctrl((enum gps_dl_link_id_enum)2, false, false);
    assert(warnings == 96);
    assert(selections == 0 && gpio_requests == 0);
    puts("actual LNA control helper: all transitions refused without hardware IO");
    return 0;
}
