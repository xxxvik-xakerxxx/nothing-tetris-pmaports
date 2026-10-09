#!/usr/bin/env python3
"""Apply the disabled first-start backend; native C fault tests are CI-only."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("powercheck", ROOT / "scripts/check-mt6878-modem-power.py")
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
PATCH = "0117-soc-mediatek-mt6878-ccci-first-start-backend.patch"
SOURCE = "drivers/soc/mediatek/mt6878-ccci-start.c"
PUBLIC = "include/linux/soc/mediatek/mt6878_ccci_start.h"
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"


def check_vendor(tree):
    def read(name):
        return subprocess.check_output(["git", "show", f"{VENDOR}:{name}"], cwd=tree, text=True)

    platform = read("drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c")
    header = read("drivers/misc/mediatek/eccci/fsm/md_sys1_platform.h")
    dt = read("arch/arm64/boot/dts/mediatek/mt6878.dts")
    table = platform.split("md_reg_table[] = {", 1)[1].split("};", 1)[0]
    assert re.findall(r'"(md-[^"]+)"', table) == [
        "md-vmodem", "md-vnr", "md-vmdfe", "md-vsram", "md-vdigrf"]
    for name, rail, voltage in [("md-vmodem", "mt6363_vbuck2", 800000),
                                ("md-vsram", "mt6363_vsram_modem", 800000),
                                ("md-vdigrf", "mt6363_vbuck1", 700000)]:
        assert re.search(rf"{name}-supply\s*=\s*<&{rail}>;", dt)
        assert re.search(rf"{name}\s*=\s*<{voltage}\s+{voltage}>;", dt)
    assert "mediatek,power-flow-config" not in dt
    assert re.search(r"SRCCLKENA_SETTING_BIT,\s*SRCLKEN_O1_BIT,\s*"
                     r"REVERT_SEQUENCER_BIT,\s*MD_PLL_SETTING,", header)
    body = platform.split("static int md_cd_power_on(struct ccci_modem *md)", 1)[1]
    sequence = ["md1_pmic_setting_on();", "md_cd_topclkgen_on(md)",
                "md_cd_srcclkena_setting(md)", "mtk_ccci_cfg_srclken_o1_on(md)",
                "flight_mode_set_by_atf(md, false);", "pm_runtime_get_sync(", "md_pll_setting(md);"]
    positions = [body.index(item) for item in sequence]
    assert positions == sorted(positions)
    assert '"md_vsram") == 0)' in platform and '"md-vsram"' in table
    print(f"Vendor {VENDOR}: rail overrides, order, flow bits and delay-name mismatch PASS")

HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint64_t resource_size_t;
#define U32_MAX UINT32_MAX
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((UINT32_MAX << (l)) & (UINT32_MAX >> (31-(h))))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p)||IS_ERR(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define EXPORT_SYMBOL_GPL(x)
#define MODULE_LICENSE(x)
#define GFP_KERNEL 0
#define dev_err(...) ((void)0)
typedef struct {int counter;} atomic_t;
#define ATOMIC_INIT(v) {v}
static int atomic_read(const atomic_t *a){return a->counter;}
static int atomic_cmpxchg(atomic_t *a,int old,int new_value){int v=a->counter;if(v==old)a->counter=new_value;return v;}
struct mutex {int held;};
static void mutex_init(struct mutex *m){m->held=0;}
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
enum role {MD,PROVIDER,SPM,IFR,NEMI,TOP,RAIL0,RAIL1,RAIL2};
struct device_node {enum role role;const char *compatible;resource_size_t start,size;int refs;};
struct device {struct device_node *of_node;void *pm_domain;struct {atomic_t usage_count;} power;};
struct regulator {int id;};
struct regmap {int id;u32 words[1024];};
struct resource {resource_size_t start,end;};
struct of_phandle_args {struct device_node *np;int args_count;u32 args[1];};
struct arm_smccc_res {u64 a0,a1,a2,a3;};
static struct device_node nodes[9];
static struct device dev;
static struct regmap maps[4];
static struct regulator rails[3];
static int calls,fail_at,smc_count,release_count,runtime_count,gate_count,transport_count;
static int runtime_return,invalid_flow,invalid_domain,stuck_write,done_override,positive_gate;
static unsigned verified;
static u64 release_reply[4];
static int missing_supply;
static u64 flags[4];
static bool wrong_clock;
static const char *trace[256];
static void *allocations[16];
static int allocations_count;
static int record(const char *name){assert(calls<256);trace[calls++]=name;return calls==fail_at?-EIO:0;}
static void *devm_kzalloc(struct device *d,size_t size,int flag){(void)d;(void)flag;
    void *p=calloc(1,size);assert(p && allocations_count<16);allocations[allocations_count++]=p;return p;}
static bool of_machine_is_compatible(const char *s){return !strcmp(s,"nothing,tetris");}
static bool of_device_is_compatible(struct device_node *n,const char *s){return n &&
    (!strcmp(s,n->compatible) || (!strcmp(s,"syscon") && n->role>=SPM));}
static bool of_device_is_available(struct device_node *n){return n && !(invalid_domain && n->role==PROVIDER);}
static bool of_property_present(struct device_node *n,const char *s){(void)n;
    if(strstr(s,"-supply"))return !missing_supply &&
        (!strcmp(s,"md-vmodem-supply") || !strcmp(s,"md-vsram-supply") || !strcmp(s,"md-vdigrf-supply"));
    return invalid_flow && !strcmp(s,"mediatek,power-flow-config");}
static int of_property_read_u32(struct device_node *n,const char *s,u32 *v){(void)n;
    int e=record(s);if(e)return e;
    *v=!strcmp(s,"mediatek,ap-plat-info")?6878:!strcmp(s,"mediatek,md-generation")?6299:invalid_flow;return 0;}
static int of_property_count_u32_elems(struct device_node *n,const char *s){(void)n;(void)s;return 2;}
static int rail_id(const char *s){return !strcmp(s,"md-vmodem")?0:!strcmp(s,"md-vsram")?1:2;}
static int of_property_read_u32_array(struct device_node *n,const char *s,u32 *pair,int count){
    (void)n;assert(count==2);int e=record("rail-voltage-dt");if(e)return e;
    pair[0]=pair[1]=rail_id(s)==2?700000:800000;return 0;}
static int of_count_phandle_with_args(struct device_node *n,const char *s,const char *p){
    (void)n;(void)p;return !strcmp(s,"power-domains")?1:2;}
static int of_parse_phandle_with_args(struct device_node *n,const char *s,const char *p,int i,struct of_phandle_args *a){
    (void)n;(void)s;(void)p;assert(i==0);int e=record("domain-phandle");if(e)return e;
    a->np=&nodes[PROVIDER];a->np->refs++;a->args_count=1;a->args[0]=0;return 0;}
static struct device_node *of_get_parent(struct device_node *n){assert(n->role==PROVIDER);nodes[SPM].refs++;return &nodes[SPM];}
static struct device_node *of_parse_phandle(struct device_node *n,const char *s,int i){
    struct device_node *r;
    if(strstr(s,"-supply")) {
        assert(n->role==MD && !i);
        if(missing_supply)return NULL;
        r=&nodes[!strcmp(s,"md-vmodem-supply")?RAIL0:!strcmp(s,"md-vsram-supply")?RAIL1:RAIL2];
    }
    else if(!strcmp(s,"ccci-topckgen")){assert(n->role==MD && !i);r=&nodes[TOP];}
    else{assert(n->role==PROVIDER && i<2);r=&nodes[i?NEMI:IFR];}r->refs++;return r;}
static void of_node_put(struct device_node *n){if(n){assert(n->refs>0);n->refs--;}}
static int of_address_to_resource(struct device_node *n,int index,struct resource *r){
    if(!n || index) {
        return -EINVAL;
    }
    int e=record("resource");if(e)return e;
    assert((verified & 3)==3);
    r->start=n->start;r->end=n->start+n->size-1;return 0;}
static resource_size_t resource_size(struct resource *r){return r->end-r->start+1;}
static struct regmap *device_node_to_regmap(struct device_node *n){int e=record("regmap");return e?ERR_PTR(e):&maps[n->role-SPM];}
static bool pm_runtime_enabled(struct device *d){(void)d;return true;}
static bool pm_runtime_status_suspended(struct device *d){(void)d;return runtime_count==0;}
static struct regulator *devm_regulator_get(struct device *d,const char *name){(void)d;
    int e=record("regulator-get");return e?ERR_PTR(e):&rails[rail_id(name)];}
static int regulator_set_voltage(struct regulator *r,int min,int max){
    assert(verified & BIT(2));
    assert(min==max && min==(r->id==2?700000:800000));return record("regulator-set");}
static int regulator_sync_voltage(struct regulator *r){(void)r;return record("regulator-sync");}
static int regmap_read(struct regmap *m,u32 off,u32 *v){int e=record("regmap-read");if(e)return e;
    assert((verified & 3)==3);
    *v=m->words[off/4];if(wrong_clock && m->id==3)*v|=BIT(8);return 0;}
static int update(struct regmap *m,u32 off,u32 bits,bool set){
    assert(verified & BIT(2));
    assert((m->id==3 && !off && !set && bits==(BIT(8)|BIT(9))) ||
        (m->id==0 && ((off==0xe00 && bits==BIT(2)) || (off==0xf24 && bits==3))));
    int e=record(set?"regmap-set":"regmap-clear");if(e)return e;
    if(set)m->words[off/4]|=bits;else m->words[off/4]&=~bits;
    if(m->id==0 && off==0xe00 && calls!=stuck_write){m->words[off/4]&=~GENMASK(31,30);
        if(m->words[off/4]&BIT(2))m->words[off/4]|=GENMASK(31,30);}
    return 0;
}
static int regmap_clear_bits(struct regmap *m,u32 o,u32 b){return update(m,o,b,false);}
static int regmap_set_bits(struct regmap *m,u32 o,u32 b){return update(m,o,b,true);}
static int regmap_write(struct regmap *m,u32 off,u32 bits){
    assert(m->id==1 || m->id==2);int e=record("bus-write");if(e)return e;
    u32 sta=off==0xc54 || off==0xc58?0xc5c:off==0xc44 || off==0xc48?0xc4c:0x8c;
    bool set=off==0xc54 || off==0xc44 || off==0x84;
    if(calls!=stuck_write){if(set)m->words[sta/4]|=bits;else m->words[sta/4]&=~bits;}
    return 0;
}
#define MTK_POLL_DELAY_US 10
#define MTK_POLL_TIMEOUT 1000000
#define PWR_ON_BIT BIT(2)
#define MTK_SCPD_MT6878_MD BIT(15)
#define MTK_SCPD_KEEP_DEFAULT_OFF BIT(3)
#define MTK_SCPD_STATUS_IN_CTL BIT(12)
#define MTK_SCPD_SKIP_RESET_B BIT(11)
enum scpsys_bus_prot_block {BUS_PROT_BLOCK_INFRA,BUS_PROT_BLOCK_NEMICFG};
struct scpsys_bus_prot_data {int bus_prot_block;u32 bus_prot_set_clr_mask,bus_prot_set,bus_prot_clr,bus_prot_sta_mask,bus_prot_sta;};
#define BUS_PROT_WR(b,m,s,c,a) {BUS_PROT_BLOCK_##b,m,s,c,m,a}
struct scpsys_domain_data {const char *name;u32 sta_mask,ctl_offs,pwr_sta_offs,pwr_sta2nd_offs,caps;struct scpsys_bus_prot_data bp_cfg[3];};
struct scpsys_soc_data {const struct scpsys_domain_data *domains_data;int num_domains;
    enum scpsys_bus_prot_block *bus_prot_blocks;int num_bus_prot_blocks;};
struct generic_pm_domain {int unused;};
struct scpsys {struct regmap *base,*maps[2];void *dev;};
struct scpsys_domain {struct generic_pm_domain genpd;struct scpsys *scpsys;
    const struct scpsys_domain_data *data;int md_error;bool md_owned;};
#define to_scpsys_domain(g) ((struct scpsys_domain *)(g))
#define regmap_read_poll_timeout(m,o,v,cond,d,t) \
    ({int e=regmap_read(m,o,&v);e?e:((cond)?0:-ETIMEDOUT);})
static struct regmap *scpsys_bus_protect_get_regmap(struct scpsys_domain *p,const struct scpsys_bus_prot_data *b){return p->scpsys->maps[b->bus_prot_block];}
#include "mt6878-modem-pm.h"
static struct scpsys scp;
static struct scpsys_domain pd;
static int pm_runtime_resume_and_get(struct device *d){
    assert(verified & BIT(3));
    assert(d->pm_domain==&pd.genpd);int e=record("runtime-resume");if(e)return e;
    if(runtime_return<0)return runtime_return;
    e=mt6878_md_power_on(&pd.genpd);if(e)return e;
    runtime_count++;d->power.usage_count.counter++;return runtime_return;
}
static void arm_smccc_smc(u32 fid,u32 req,u32 cmd,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,struct arm_smccc_res *r){
    assert((verified & 3)==3);
    if(req==7)assert(verified & BIT(3));
    if(req==6 && !cmd)assert(verified & BIT(4));
    assert(fid==0xc2000505 && !a && !b && !c && !d && !e);
    assert((req==6 && (cmd==0 || cmd==2 || cmd==3)) || (req==7 && !cmd));
    int fault=record("secure");smc_count++;*r=(struct arm_smccc_res){0};
    if(fault){r->a0=UINT64_MAX;return;}
    if(req==6 && cmd==3){r->a0=done_override;r->a1=r->a2=r->a3=1;}
    if(req==6 && cmd==2){r->a0=flags[0];r->a1=flags[1];r->a2=flags[2];r->a3=flags[3];}
    if(req==6 && cmd==0){assert(pd.md_owned && runtime_count==1);release_count++;
        *r=(struct arm_smccc_res){release_reply[0],release_reply[1],release_reply[2],release_reply[3]};}
}
#include "mt6878_ccci_start.h"
static int verify(struct device *d,void *o,enum mt6878_ccci_start_gate gate){
    (void)d;(void)o;gate_count++;int e=record("evidence-gate");
    if(e || positive_gate==(int)gate+1)return e?e:1;
    assert(gate_count==(int)gate+1);
    verified|=BIT(gate);return 0;}
static int prepare(struct device *d,void *o){(void)d;(void)o;
    assert(pd.md_owned && runtime_count==1);transport_count++;return record("transport");}
#include "mt6878-ccci-start.c"
static void setup(void){
    for(int i=0;i<allocations_count;i++) {
        free(allocations[i]);
    }
    allocations_count=0;
    mt6878_ccci_attempted.counter=0;
    calls=fail_at=smc_count=release_count=runtime_count=gate_count=transport_count=0;
    runtime_return=invalid_flow=invalid_domain=stuck_write=done_override=positive_gate=0;wrong_clock=false;
    verified=0;
    missing_supply=0;
    release_reply[0]=release_reply[1]=release_reply[2]=0;release_reply[3]=1;
    nodes[MD]=(struct device_node){.role=MD,.compatible="mediatek,mddriver"};
    nodes[PROVIDER]=(struct device_node){.role=PROVIDER,.compatible="mediatek,mt6878-modem-power-controller"};
    for(int i=0;i<3;i++)nodes[RAIL0+i]=(struct device_node){.role=RAIL0+i,.compatible="mt6363-regulator"};
    const char *compat[]={"mediatek,mt6878-scpsys","mediatek,mt6878-infracfg-ao",
        "mediatek,mt6878-nemicfg_ao_mem_reg_bus","mediatek,mt6878-topckgen"};
    const u32 addresses[]={0x1c001000,0x10001000,0x10270000,0x10000000};
    for(int i=0;i<4;i++){nodes[i+SPM]=(struct device_node){.role=i+SPM,.compatible=compat[i],.start=addresses[i],.size=0x1000};
        maps[i]=(struct regmap){.id=i};}
    maps[0].words[0xe00/4]=BIT(0);maps[0].words[0xf24/4]=3;
    maps[1].words[0xc5c/4]=BIT(9);maps[1].words[0xc4c/4]=BIT(11);maps[2].words[0x8c/4]=BIT(6)|BIT(7);
    maps[3].words[0]=BIT(8)|BIT(9)|BIT(5);
    scp=(struct scpsys){.base=&maps[0],.maps={&maps[1],&maps[2]}};
    pd=(struct scpsys_domain){.scpsys=&scp,.data=&mt6878_md_domains[0]};
    dev=(struct device){.of_node=&nodes[MD],.pm_domain=&pd.genpd};
    for(int i=0;i<3;i++)rails[i]=(struct regulator){.id=i};
    for(int i=0;i<4;i++)flags[i]=1;
}
static struct mt6878_ccci_start *allocate(void){
    const struct mt6878_ccci_start_callbacks cb={verify,prepare};
    struct mt6878_ccci_start *s=mt6878_ccci_start_alloc(&dev,NULL,&cb);assert(!IS_ERR(s));return s;
}
static void invariant(void){assert(maps[0].words[0xe00/4]&BIT(0));assert(!(maps[0].words[0xe00/4]&BIT(3)));
    assert(maps[3].words[0]&BIT(5));for(int i=0;i<9;i++)assert(!nodes[i].refs);}
int main(void){
    setup();assert(IS_ERR(mt6878_ccci_start_alloc(&dev,NULL,NULL)));assert(!calls);
    struct mt6878_ccci_start *s=allocate();assert(!calls);
    assert(mt6878_ccci_first_start(s)==0);int total=calls;
    assert(s->result.stage==MT6878_CCCI_COMPLETE && s->result.execution_released);
    assert(s->result.execution_release_attempted);
    assert(s->result.runtime_reference && release_count==1 && runtime_count==1 && gate_count==5 && smc_count==4);
    assert(s->result.power_reads==5);
    int power_write=0,bus_write=0;
    for(int i=0;i<total;i++) {
        if(!power_write && !strcmp(trace[i],"regmap-set"))power_write=i+1;
        if(!bus_write && !strcmp(trace[i],"bus-write"))bus_write=i+1;
    }
    assert(power_write && bus_write);
    invariant();struct mt6878_ccci_start_result result;mt6878_ccci_start_result(s,&result);
    assert(result.execution_released && calls==total);
    assert(mt6878_ccci_first_start(s)==-EALREADY && calls==total);
    struct mt6878_ccci_start *second=allocate();assert(mt6878_ccci_first_start(second)==-EALREADY && calls==total);
    for(int fault=1;fault<=total;fault++){
        setup();s=allocate();fail_at=fault;int e=mt6878_ccci_first_start(s);
        assert(e<0 && s->result.first_error==e && calls==fault && !s->result.execution_released);
        assert(mt6878_ccci_first_start(s)==e && calls==fault);
        if(s->result.stage>MT6878_CCCI_POWER)assert(s->result.runtime_reference);
        invariant();
    }
    const u64 not_ready[]={0,2,0xffffffff};
    for(int field=0;field<4;field++){
        for(unsigned value=0;value<ARRAY_SIZE(not_ready);value++) {
            setup();s=allocate();flags[field]=not_ready[value];
            assert(mt6878_ccci_first_start(s)==-ENODATA);
            assert(s->result.stage==MT6878_CCCI_BROM_FLAGS && !runtime_count && !release_count);
            assert(s->result.secure[field]==not_ready[value]);invariant();
        }
    }
    setup();s=allocate();flags[0]=UINT64_MAX;
    assert(mt6878_ccci_first_start(s)==-EPROTO && !runtime_count);
    setup();s=allocate();done_override=1;
    assert(mt6878_ccci_first_start(s)==-EAGAIN && smc_count==1 && !runtime_count);
    for(int flow=1;flow<16;flow++) {
        setup();s=allocate();invalid_flow=flow;
        assert(mt6878_ccci_first_start(s)==-EOPNOTSUPP && smc_count==0);
    }
    setup();s=allocate();invalid_domain=1;
    assert(mt6878_ccci_first_start(s)==-EINVAL && smc_count==0);
    setup();s=allocate();maps[0].words[0xe00/4]|=BIT(2)|GENMASK(31,30);
    assert(mt6878_ccci_first_start(s)==-EBUSY && !runtime_count && !release_count);
    setup();s=allocate();wrong_clock=true;
    assert(mt6878_ccci_first_start(s)==-EIO && !runtime_count);
    setup();s=allocate();runtime_return=1;
    assert(mt6878_ccci_first_start(s)==0 && runtime_count==1 && release_count==1);invariant();
    setup();s=allocate();runtime_return=-ETIMEDOUT;
    assert(mt6878_ccci_first_start(s)==-ETIMEDOUT && !s->result.runtime_reference && !release_count);
    setup();s=allocate();positive_gate=1;
    assert(mt6878_ccci_first_start(s)==-EPROTO && calls==1 && !smc_count);
    for(int gate=2;gate<=5;gate++) {
        setup();s=allocate();positive_gate=gate;
        assert(mt6878_ccci_first_start(s)==-EPROTO && gate_count==gate && !release_count);
        assert(!s->result.execution_release_attempted);
        if(gate<=3)assert(!runtime_count);
        if(gate==5)assert(s->result.runtime_reference && runtime_count==1);
        int before=calls;assert(mt6878_ccci_first_start(s)==-EPROTO && calls==before);invariant();
    }
    setup();s=allocate();missing_supply=1;
    assert(mt6878_ccci_first_start(s)==-EINVAL && !runtime_count && !release_count);
    assert(maps[3].words[0]&(BIT(8)|BIT(9)));
    for(int which=0;which<2;which++) {
        setup();s=allocate();stuck_write=which?bus_write:power_write;
        assert(mt6878_ccci_first_start(s)==-ETIMEDOUT);
        assert(pd.md_error==-ETIMEDOUT && !release_count && !s->result.runtime_reference);
        int before=calls;
        mt6878_md_cleanup(&pd);assert(calls==before);
        assert(mt6878_ccci_first_start(s)==-ETIMEDOUT && calls==before);invariant();
    }
    for(int field=0;field<4;field++) {
        setup();s=allocate();release_reply[field]=UINT64_MAX;
        assert(mt6878_ccci_first_start(s)==-EPROTO && s->result.runtime_reference);
        assert(!s->result.execution_released && release_count==1 && runtime_count==1);
        assert(s->result.execution_release_attempted);
        int before=calls;assert(mt6878_ccci_first_start(s)==-EPROTO && calls==before);invariant();
    }
    setup(); /* Exercise the real provider's cleanup guard without starting a transaction. */
    mt6878_md_cleanup(&pd);assert(!calls);
    assert(mt6878_md_scpsys_data.num_domains==1);
    setup();
    puts("CCCI first-start: real provider, typed secure ABI, all external faults, data flags, gates, latch PASS");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--vendor", type=Path, help="offline checkout containing the pinned B4.1 commit")
    args = parser.parse_args()
    if args.native_ci and os.environ.get("CI") != "true":
        parser.error("native compilation is CI-only")
    if args.vendor:
        check_vendor(args.vendor)
    power.FILES.update({SOURCE, PUBLIC, "drivers/soc/mediatek/Kconfig", "drivers/soc/mediatek/Makefile"})
    with tempfile.TemporaryDirectory(prefix="tetris-ccci-start-") as directory:
        out = Path(directory)
        for name in power.FILES:
            base = args.kernel / name
            if base.exists():
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(base, out / name)
        names = re.findall(r"^\s+([\w.-]+\.patch)$", (power.PACKAGE / "APKBUILD").read_text(), re.M)
        for name in dict.fromkeys(names + [power.PATCH.name, PATCH]):
            selected = "".join(power.sections((power.PACKAGE / name).read_text(encoding="latin-1")))
            if selected:
                subprocess.run(["git", "apply", "-"], cwd=out, input=selected, text=True, check=True)
        code = (out / SOURCE).read_text()
        assert "pm_runtime_resume_and_get(s->dev)" in code
        assert "#define STEP(stage_id, operation)" in code
        assert "#define STEP(stage, operation)" not in code
        assert "PWR_RST_B" not in code and "0xc200040b" not in code
        assert "pm_runtime_put" not in code and "module_platform_driver" not in code
        execute = code.split("static int mt6878_ccci_execute(", 1)[1].split("int mt6878_ccci_first_start(", 1)[0]
        ordered = ["STEP(AUTH,", "STEP(PROFILE,", "MT6878_CCCI_EXCLUSIVE_OFF_BOOT_INHIBITED",
                   "STEP(BINDING,", "STEP(BROM_DONE,", "STEP(BROM_FLAGS,", "mt6878_ccci_state(s, false)",
                   "MT6878_CCCI_BEFORE_RESOURCES", "STEP(RAILS,", "STEP(CLOCK,", "MT6878_CCCI_BEFORE_POWER",
                   "STEP(FLIGHT,", "pm_runtime_resume_and_get(s->dev)", "STEP(POWER_ACK,", "STEP(TRANSPORT,",
                   "MT6878_CCCI_BEFORE_EXECUTION", "execution_release_attempted = true", "STEP(RELEASE,"]
        positions = [execute.index(item) for item in ordered]
        assert positions == sorted(positions), "ownership/mutation/secure/release gate order changed"
        config = (out / "drivers/soc/mediatek/Kconfig").read_text()
        stanza = config.split("config MTK_MT6878_CCCI_FIRST_START", 1)[1].split("\nconfig ", 1)[0]
        assert "default y" not in stanza
        print("Disabled backend applies; provider/secure boundary and no reset/retry/cleanup checks PASS")
        if args.native_ci:
            native = out / "native"
            native.mkdir()
            for name, target in [(SOURCE, "mt6878-ccci-start.c"), (PUBLIC, "mt6878_ccci_start.h")]:
                text = re.sub(r"^#include <linux/[^\n]+>\n", "", (out / name).read_text(), flags=re.M)
                (native / target).write_text(text)
            shutil.copyfile(out / "drivers/pmdomain/mediatek/mt6878-modem-pm.h", native / "mt6878-modem-pm.h")
            (native / "test.c").write_text(HARNESS)
            subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", str(native / "test.c"),
                            "-o", str(native / "test")], check=True)
            subprocess.run([str(native / "test")], check=True)


if __name__ == "__main__":
    main()
