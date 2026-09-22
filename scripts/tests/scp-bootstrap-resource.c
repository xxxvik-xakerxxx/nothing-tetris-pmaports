#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>

#define module_param(name, type, mode) _Static_assert((mode) == 0444, "read-only parameter")
#define MODULE_PARM_DESC(name, text) _Static_assert(sizeof(text) > 1, "description")
#define pr_notice(...) ((void)0)
#define pr_err(...) ((void)0)
#define SCP_REQ_RELEASE 0
#define SCP_REQ_26M 1
static int dvfs_enabled, response, calls, last_vote;
static int scp_dvfs_feature_enable(void) { return dvfs_enabled; }
static int scp_resource_req(unsigned int vote)
{
    calls++;
    last_vote = vote;
    return response;
}

/* INSERT_PATCHED_HELPERS */

int main(void)
{
    assert(!bootstrap_26m && !bootstrap_26m_held);
    assert(scp_bootstrap_resource_get() == 0);
    scp_bootstrap_resource_put();
    assert(calls == 0);

    bootstrap_26m = true;
    dvfs_enabled = 1;
    assert(scp_bootstrap_resource_get() == -EINVAL);
    assert(calls == 0 && !bootstrap_26m_held);
    dvfs_enabled = 0;
    response = -EACCES;
    assert(scp_bootstrap_resource_get() == -EACCES);
    assert(calls == 1 && !bootstrap_26m_held);
    scp_bootstrap_resource_put();
    assert(calls == 1);
    response = 2;
    assert(scp_bootstrap_resource_get() == -EIO);
    assert(calls == 2 && !bootstrap_26m_held);

    response = 0;
    assert(scp_bootstrap_resource_get() == 0);
    assert(calls == 3 && last_vote == SCP_REQ_26M && bootstrap_26m_held);
    assert(scp_bootstrap_resource_get() == -EBUSY);
    assert(calls == 3);
    response = -EIO;
    scp_bootstrap_resource_put();
    assert(calls == 4 && last_vote == SCP_REQ_RELEASE && bootstrap_26m_held);
    response = 0;
    scp_bootstrap_resource_put();
    assert(calls == 5 && !bootstrap_26m_held);
    scp_bootstrap_resource_put();
    assert(calls == 5);
    puts("PASS: bootstrap resource defaults, ownership, errors and cleanup");
    return 0;
}
