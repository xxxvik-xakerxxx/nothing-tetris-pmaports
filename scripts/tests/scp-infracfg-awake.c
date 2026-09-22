#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <stdarg.h>
#define SCP_RECOVERY_SUPPORT 0
#define SCP_AWAKE_TIMEOUT 4
#define EXPORT_SYMBOL_GPL(x)
#define WARN_ON(x) ((void)(x))
#define AP_AWAKE_LOCK 0
#define AP_AWAKE_UNLOCK 1
#define INFRA_IRQ_SET 0xb14
#define INFRA_IRQ_CLEAR 0xb18
enum scp_core_id { SCP_A_ID, SCP_CORE_TOTAL };
static int scp_awake_counts[1], scp_awake_spinlock;
static char *core_ids[] = { "SCP A" };
static struct { void *scpsys; } scpreg;
static int set_error, read_error, clear_error, writes, reads, locked;
static bool ready, ack, wdt;
static unsigned int pending;
static void quiet(const char *format, ...) { (void)format; }
#define pr_notice quiet
#define pr_err quiet
#define spin_lock_irqsave(lock, flags) do { \
    (void)(lock); (flags) = 0; assert(!locked); locked = 1; \
} while (0)
#define spin_unlock_irqrestore(lock, flags) do { \
    (void)(lock); (void)(flags); assert(locked); locked = 0; \
} while (0)
static int is_scp_ready(enum scp_core_id id) { assert(id == SCP_A_ID); return ready; }
static bool scp_wdt_pending_check(int id) { assert(!id); return wdt; }
static void udelay(int us) { assert(us == 10); }
static int regmap_write(void *map, unsigned int reg, unsigned int val)
{
    assert(map == &scpreg && locked);
    assert(val == 0xa1 || val == 0xa2);
    writes++;
    if (reg == INFRA_IRQ_SET) { pending = val; return set_error; }
    assert(reg == INFRA_IRQ_CLEAR && val == pending);
    return clear_error;
}
static int regmap_read(void *map, unsigned int reg, unsigned int *val)
{
    assert(map == &scpreg && reg == INFRA_IRQ_SET && locked);
    reads++;
    *val = ack ? 0xa0 : pending;
    return read_error;
}

/* INSERT_PATCHED_AWAKE */

static void reset(void)
{
    assert(!locked);
    scpreg.scpsys = &scpreg;
    scp_awake_counts[0] = 0;
    set_error = read_error = clear_error = writes = reads = 0;
    ready = ack = true;
    wdt = false;
}
static void check(bool unlock, int result, int count)
{
    assert((unlock ? scp_awake_unlock(NULL) : scp_awake_lock(NULL)) == result);
    assert(!locked && scp_awake_counts[0] == count);
}
int main(void)
{
    reset(); check(false, 0, 1); assert(writes == 2 && reads == 1);
    check(true, 0, 0); assert(writes == 4 && reads == 2);
    reset(); scp_awake_counts[0] = 1; check(false, 0, 2);
    check(true, 0, 1); assert(!writes && !reads);
    for (int unlock = 0; unlock < 2; unlock++) {
        reset(); scp_awake_counts[0] = unlock; ready = false;
        check(unlock, -1, unlock); assert(!writes && !reads);
        reset(); scp_awake_counts[0] = unlock; set_error = -5;
        check(unlock, -1, unlock); assert(writes == 1 && !reads);
        reset(); scp_awake_counts[0] = unlock; read_error = -5;
        check(unlock, -1, unlock); assert(writes == 2 && reads == 1);
        reset(); scp_awake_counts[0] = unlock; clear_error = -5;
        check(unlock, -1, unlock); assert(writes == 2 && reads == 1);
        reset(); scp_awake_counts[0] = unlock; ack = false;
        check(unlock, -1, unlock); assert(writes == 2 && reads == 3);
        reset(); scp_awake_counts[0] = unlock; wdt = true;
        check(unlock, -1, unlock); assert(writes == 2 && !reads);
    }
    puts("PASS: shared-regmap wake lock/unlock, nesting and six failure paths");
    return 0;
}
