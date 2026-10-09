#!/usr/bin/env python3
"""Bundle/apply the opt-in CCCI owner; compile native fault fixtures only in CI."""
import argparse
import difflib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("first_start", HERE / "check_first_start.py")
first = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first)
VENDOR = first.VENDOR
PREFIX = "drivers/misc/mediatek/eccci/"
NEW = {PREFIX + "inc/ccci_tetris_owner.h": HERE / "ccci_tetris_owner.h",
       PREFIX + "fsm/ccci_tetris_owner.c": HERE / "ccci_tetris_owner.c",
       PREFIX + "hif/ccci_tetris_hif_owned.c": HERE / "ccci_tetris_hif_owned.c"}


def bundle():
    result = (HERE / "owner-integration.patch.vendor").read_text()
    for name, source in NEW.items():
        result += f"diff --git a/{name} b/{name}\nnew file mode 100644\n"
        result += "".join(difflib.unified_diff([], source.read_text().splitlines(True),
                                              fromfile="/dev/null", tofile="b/" + name))
    return result


def apply_patch(out, text):
    subprocess.run(["git", "apply", "-"], cwd=out, input=text, text=True, check=True)


def prepare_vendor(vendor, out):
    text = bundle()
    names = re.findall(r"^diff --git a/(\S+) b/", text, re.M)
    for name in names:
        if name in NEW:
            continue
        content = subprocess.check_output(["git", "show", f"{VENDOR}:{name}"], cwd=vendor)
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    power = first.power
    saved = power.FILES.copy()
    power.FILES.clear()
    power.FILES.update(names)
    try:
        patches = re.findall(r"^\s+([\w.-]+\.patch\.vendor)$", (power.PACKAGE / "APKBUILD").read_text(), re.M)
        for patch in dict.fromkeys(patches):
            selected = "".join(power.sections((power.PACKAGE / patch).read_text(encoding="latin-1")))
            if selected:
                apply_patch(out, selected)
    finally:
        power.FILES.clear()
        power.FILES.update(saved)
    apply_patch(out, text)
    # The shipping selection remains off; no default or DT consumer added.
    config = (out / PREFIX / "Kconfig").read_text()
    stanza = config.split("config MTK_ECCCI_TETRIS_OWNER", 1)[1].split("\nconfig ", 1)[0]
    assert "default y" not in stanza
    owner = (out / PREFIX / "fsm/ccci_tetris_owner.c").read_text()
    assert "mt6878_ccci_first_start(tetris_owner.backend)" in owner
    assert "pm_runtime_put" not in owner and "arm_smccc_smc" not in owner
    assert "dev_pm_domain_attach(" not in owner and "PWR_RST_B" not in owner
    assert "tetris_owner.proofs.verify(" in owner and "tetris_owner.proofs.transport_access(" in owner
    assert "wdt_enable_irq(md)" in owner
    ccif = (out / PREFIX / "hif/ccci_hif_ccif.c").read_text()
    late = function(ccif, "ccif_late_init")
    assert late.index("atomic_set(&ccif_ctrl->ccif_irq1_enabled, 0)") < late.index("request_irq(")
    assert "IRQF_NO_AUTOEN" in late
    for source, name in [("fsm/modem_sys1.c", "ccci_tetris_wdt_init_owned"),
                         ("fsm/ccci_fsm.c", "ccci_tetris_publish_hs1"),
                         ("hif/ccci_hif_ccif.c", "ccif_start"),
                         ("hif/ccci_dpmaif_com.c", "dpmaif_start")]:
        check_delimiters(function((out / PREFIX / source).read_text(), name))
    check_delimiters(EXTRA)
    check_delimiters(owner)
    print("Owner bundle applies after integrated vendor patches; default off, real proof hooks and powered transport PASS")


def function(text, name):
    match = re.search(rf"^(?:static )?(?:int|void) {name}\([^;]+?\n\{{\n.*?^\}}", text, re.M | re.S)
    if not match:
        raise ValueError(f"missing exact production function {name}")
    return match[0]


def check_delimiters(text):
    # Cheap source-only guard, not a substitute for the real CI compiler.
    text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  '', text, flags=re.S)
    stack = []
    for char in text:
        if char in '([{':
            stack.append(char)
        elif char in ')]}':
            assert stack and stack.pop() == {')': '(', ']': '[', '}': '{'}[char]
    assert not stack


EXTRA = r'''
#define DEFINE_MUTEX(n) struct mutex n={0}
struct module {int refs;};
static struct module self_module,proof_module,ccif_module,dpmaif_module;
#define THIS_MODULE (&self_module)
static bool try_module_get(struct module *m){
    int e=record("module-pin");
    if(e){return false;}
    if(m){m->refs++;}
    return true;
}
static void module_put(struct module *m){
    if(m){assert(m->refs>0);m->refs--;}
}
enum CCCI_HIF {CLDMA_HIF_ID,CCIF_HIF_ID,DPMAIF_HIF_ID,CCCI_HIF_NUM};
#define MD_SETTING_FIRST_BOOT BIT(0)
#define IRQF_NO_AUTOEN BIT(1)
struct platform_device {struct device dev;};
struct ccci_plat_val {unsigned md_gen;};
struct md_hw_info {struct ccci_plat_val *plat_val;};
struct ccci_modem {
    struct platform_device *plat_dev;struct md_hw_info *hw_info;unsigned hif_flag;
    struct {struct {unsigned setting;} config;int is_in_ee_dump;} per_md_data;
    atomic_t reset_on_going,wdt_enabled;int is_force_asserted,md_wdt_irq_id;unsigned md_wdt_irq_flags;
};
struct ccci_hif_ops {struct module *owner;int (*start)(unsigned char);};
static struct ccci_hif_ops *ccci_hif_op[CCCI_HIF_NUM];
static void *ccci_hif[CCCI_HIF_NUM];
static bool wdt_requested,wdt_enabled,hs1_published;
static int positive_transport;
static int md_cd_wdt_isr(int irq,void *md){(void)irq;(void)md;return 0;}
static int request_irq(int irq,int (*handler)(int,void *),unsigned flags,const char *name,void *md){
    (void)irq;(void)handler;(void)name;(void)md;assert(flags&IRQF_NO_AUTOEN);
    assert(pd.md_owned && runtime_count==1);int e=record("wdt-request");if(!e)wdt_requested=true;return e;}
static int irq_set_irq_wake(int irq,int on){(void)irq;assert(on==1);return record("wdt-wake");}
void wdt_enable_irq(struct ccci_modem *md){assert(wdt_requested && hs1_published && release_count==1);
    assert(!atomic_read(&md->wdt_enabled));md->wdt_enabled.counter=1;wdt_enabled=true;}
enum {CCCI_FSM_STARTING,BOOT_WAITING_FOR_HS1};
struct ccci_fsm_ctl {int curr_state;};
static struct ccci_fsm_ctl fsm,*ccci_fsm_entries=&fsm;
static int fsm_broadcast_state(struct ccci_fsm_ctl *ctl,int state){
    assert(ctl==&fsm && state==BOOT_WAITING_FOR_HS1 && runtime_count==1);
    int e=record("publish-waiting-hs1");if(!e)hs1_published=true;return e;}
static int hif_start(unsigned char id){assert(pd.md_owned && runtime_count==1 && wdt_requested);
    assert(id==CCIF_HIF_ID || id==DPMAIF_HIF_ID);return record(id==CCIF_HIF_ID?"ccif-start":"dpmaif-start");}
static int owner_transport_access(struct device *d,void *o){(void)d;(void)o;
    assert(pd.md_owned && runtime_count==1);int e=record("transport-access-proof");return e?e:positive_transport;}
struct clk {int id;};
struct ccci_clk_node {struct clk *clk_ref;const char *clk_name;};
struct dpmaif_clk_node {struct clk *clk_ref;const char *clk_name;};
static struct clk test_clocks[6];
static struct ccci_clk_node ccif_clk_table[6];
static int clock_return;
static int clk_prepare_enable(struct clk *clock){assert(clock && !IS_ERR(clock));int e=record("clock-enable");return e?e:clock_return;}
#include "ccci_tetris_owner.h"
#include "wdt.c"
#include "hs1.c"
#include "ccif-clocks.c"
#include "dpmaif-clocks.c"
#define CONFIG_MTK_ECCCI_TETRIS_OWNER 1
#define IS_ENABLED(x) (x)
#define DPMAIF_TRAFFIC_MONITOR_INTERVAL 0
#define CCCI_NORMAL_LOG(...) ((void)0)
#define spin_lock_irqsave(lock,flags) do {(void)(lock);(flags)=0;} while(0)
#define spin_unlock_irqrestore(lock,flags) do {(void)(lock);(void)(flags);} while(0)
enum {DPMAIF_STATE_MIN,DPMAIF_STATE_PWRON,HIFCCIF_STATE_MIN,HIFCCIF_STATE_PWRON};
enum {RB_EXP,RB_NORMAL,AP_MD1_CCIF};
static bool dpmaif_irq,ccif_irq,real_transport_context;
static int lower_positive,dpmaif_tail,ccif_tail,devapc_flag_lock,devapc_check_flag;
static atomic_t g_tx_busy_assert_on;
static int g_dpmf_ver=3;
struct dpmaif_fixture_ctl {int dpmaif_state,support_2rxq;struct dpmaif_clk_node *clk_tbs;};
static struct dpmaif_fixture_ctl dpmaif_controller,*dpmaif_ctl=&dpmaif_controller;
struct md_ccif_ctrl {int ccif_state,ccif_clk_free_run,ap_ccif_irq1_id;atomic_t ccif_irq1_enabled;void *ccif_ap_base,*ccif_md_base;};
static struct md_ccif_ctrl ccif_controller,*ccci_ccif_ctrl=&ccif_controller;
static int lower_step(const char *name){
    if(real_transport_context)assert(pd.md_owned && runtime_count==1 && wdt_requested);
    int e=record(name);
    return e?e:lower_positive;
}
static int dpmaif_late_init(void){return lower_step("dpmaif-late-init");}
static int dpmaif_hw_start(void){return lower_step("dpmaif-hw-start");}
static struct {int (*drv_start)(void);} ops={dpmaif_hw_start};
static int dpmaif_rxqs_start(void){return lower_step("dpmaif-rxqs");}
static int ccci_dpmaif_bat_start(void){return lower_step("dpmaif-bat");}
static int dpmaif_txqs_start(void){return lower_step("dpmaif-txqs");}
static void ccci_drv3_dl_lro_hpc_hw_init(void){dpmaif_tail++;}
static void ccci_drv3_hw_init_done(void){dpmaif_tail++;}
static void ccci_drv_clear_ip_busy(void){dpmaif_tail++;}
static void dpmaif_enable_all_irq(void){dpmaif_irq=true;}
static int ccif_late_init(unsigned char id){
    assert(id==CCIF_HIF_ID);
    atomic_set(&ccci_ccif_ctrl->ccif_irq1_enabled,0);
    return lower_step("ccif-late-init");
}
static void md_ccif_sram_reset(unsigned char id){assert(id==CCIF_HIF_ID);ccif_tail++;}
static void md_ccif_switch_ringbuf(unsigned char id,int rb){assert(id==CCIF_HIF_ID);(void)rb;ccif_tail++;}
static void md_ccif_reset_queue(unsigned char id,int direction){assert(id==CCIF_HIF_ID && direction==1);ccif_tail++;}
static void ccci_reset_ccif_hw(int id,void *ap,void *md,struct md_ccif_ctrl *ctl){
    assert(id==AP_MD1_CCIF && ctl==ccci_ccif_ctrl);(void)ap;(void)md;ccif_tail++;
}
static void enable_irq(int id){assert(id==ccci_ccif_ctrl->ap_ccif_irq1_id);assert(!ccif_irq);ccif_irq=true;}
#include "ccif-irq.c"
#include "ccif-start.c"
#include "dpmaif-start.c"
#include "ccci_tetris_hif_owned.c"
#include "ccci_tetris_owner.c"
static struct platform_device control;
static struct ccci_plat_val platform;
static struct md_hw_info hardware;
static struct ccci_modem modem;
static struct ccci_hif_ops providers[2];
static struct bus_type genpd_bus={"genpd"};
static void owner_setup(void){
    setup();memset(&tetris_owner,0,sizeof(tetris_owner));
    self_module.refs=proof_module.refs=ccif_module.refs=dpmaif_module.refs=0;
    tetris_hif_attempted=false;tetris_hif_error=0;memset(tetris_hif_modules,0,sizeof(tetris_hif_modules));
    dev.bus=&genpd_bus;control=(struct platform_device){.dev={.of_node=dev.of_node}};
    platform=(struct ccci_plat_val){.md_gen=6299};hardware=(struct md_hw_info){.plat_val=&platform};
    modem=(struct ccci_modem){.plat_dev=&control,.hw_info=&hardware,.hif_flag=BIT(CCIF_HIF_ID)|BIT(DPMAIF_HIF_ID)};
    modem.per_md_data.config.setting=MD_SETTING_FIRST_BOOT;
    for(int i=0;i<2;i++)providers[i]=(struct ccci_hif_ops){.owner=i?&dpmaif_module:&ccif_module,.start=hif_start};
    ccci_hif_op[CCIF_HIF_ID]=&providers[0];ccci_hif_op[DPMAIF_HIF_ID]=&providers[1];
    ccci_hif[CCIF_HIF_ID]=&providers[0];ccci_hif[DPMAIF_HIF_ID]=&providers[1];
    wdt_requested=wdt_enabled=hs1_published=false;positive_transport=clock_return=0;
    dpmaif_irq=ccif_irq=real_transport_context=false;
    lower_positive=dpmaif_tail=ccif_tail=devapc_check_flag=0;
    dpmaif_controller=(struct dpmaif_fixture_ctl){0};dpmaif_ctl=&dpmaif_controller;
    ccif_controller=(struct md_ccif_ctrl){.ccif_state=HIFCCIF_STATE_MIN};ccci_ccif_ctrl=&ccif_controller;
    atomic_set(&ccif_controller.ccif_irq1_enabled,1); /* Actual probe inheritance. */
    fsm.curr_state=CCCI_FSM_STARTING;
    for(int i=0;i<6;i++){test_clocks[i]=(struct clk){i};ccif_clk_table[i]=(struct ccci_clk_node){&test_clocks[i],"clock"};}
}
static int owner_bind(void){const struct ccci_tetris_proofs proof={&proof_module,verify,owner_transport_access};
    return ccci_tetris_owner_bind(&modem,&dev,NULL,&proof);}
static void real_hifs(void){
    static struct dpmaif_clk_node clocks[4];
    for(int i=0;i<3;i++)clocks[i]=(struct dpmaif_clk_node){&test_clocks[i],"clock"};
    clocks[3]=(struct dpmaif_clk_node){0};dpmaif_controller.clk_tbs=clocks;
    providers[0].start=ccif_start;providers[1].start=dpmaif_start;
    real_transport_context=true;
}
int main(void){
    owner_setup();allocate(); /* Retain use of the shared backend allocation fixture. */
    assert(ccci_tetris_owner_entry()==-ENOKEY && !calls);
    assert(!owner_bind());calls=0;assert(!ccci_tetris_owner_start(&modem));int total=calls;
    assert(wdt_enabled && hs1_published && release_count==1);
    assert(!(modem.per_md_data.config.setting&MD_SETTING_FIRST_BOOT));
    struct ccci_tetris_owner_result result;ccci_tetris_owner_result(&result);assert(calls==total && result.backend.execution_released);
    assert(ccci_tetris_owner_start(&modem)==-EALREADY && calls==total);invariant();
    for(int fault=1;fault<=total;fault++){
        owner_setup();assert(!owner_bind());calls=0;fail_at=fault;
        int e=ccci_tetris_owner_start(&modem);assert(e<0 && calls==fault && !wdt_enabled);
        assert(tetris_owner.result.first_error==e && !tetris_owner.result.backend.execution_released);
        assert(modem.per_md_data.config.setting&MD_SETTING_FIRST_BOOT);
        assert(ccci_tetris_owner_start(&modem)==e && calls==fault);
        assert(ccci_tetris_owner_latch(-ETIMEDOUT)==e && calls==fault);invariant();
    }
    owner_setup();assert(ccci_tetris_owner_start(&modem)==-ENOKEY && !calls);
    assert(owner_bind()==-EBUSY && !calls);
    owner_setup();control.dev.pm_domain=&pd.genpd;assert(owner_bind()==-EBUSY && !calls);
    owner_setup();assert(!owner_bind());calls=0;ccci_hif_op[DPMAIF_HIF_ID]=NULL;
    assert(ccci_tetris_owner_start(&modem)==-ENODEV && !release_count && !wdt_enabled);
    assert(tetris_owner.result.backend.runtime_reference);
    owner_setup();assert(!owner_bind());calls=0;positive_transport=1;
    assert(ccci_tetris_owner_start(&modem)==-EPROTO && !wdt_requested && !release_count);
    assert(tetris_owner.result.backend.runtime_reference);
    owner_setup();ccif_clk_table[5].clk_ref=NULL;assert(ccif_owner_clocks()==-ENODEV && !calls);
    for(int fault=1;fault<=6;fault++){
        owner_setup();fail_at=fault;assert(ccif_owner_clocks()==-EIO && calls==fault);
    }
    owner_setup();clock_return=1;assert(ccif_owner_clocks()==-EPROTO && calls==1);
    struct dpmaif_clk_node clocks[4];
    for(int fault=1;fault<=3;fault++){
        owner_setup();for(int i=0;i<3;i++)clocks[i]=(struct dpmaif_clk_node){&test_clocks[i],"clock"};
        clocks[3]=(struct dpmaif_clk_node){0};fail_at=fault;
        assert(dpmaif_owner_clocks(clocks)==-EIO && calls==fault);
    }
    owner_setup();assert(dpmaif_owner_clocks(NULL)==-ENODEV && !calls);
    owner_setup();clocks[0]=(struct dpmaif_clk_node){0};
    assert(dpmaif_owner_clocks(clocks)==-ENODEV && !calls);
    owner_setup();clocks[0]=(struct dpmaif_clk_node){NULL,"clock"};
    assert(dpmaif_owner_clocks(clocks)==-ENODEV && !calls);
    /* Execute both production start functions through the real dispatcher/backend.
     * Lower hardware primitives are mocks, not evidence of successful MD execution. */
    owner_setup();real_hifs();assert(!owner_bind());calls=0;
    assert(!ccci_tetris_owner_start(&modem));int real_total=calls;
    assert(ccif_irq && dpmaif_irq && wdt_enabled && release_count==1);
    assert(ccif_tail==6 && dpmaif_tail==2);
    ccif_enable_irq1(CCIF_HIF_ID); /* The real atomic guard prevents duplicate enable. */
    for(int fault=1;fault<=real_total;fault++){
        owner_setup();real_hifs();assert(!owner_bind());calls=0;fail_at=fault;
        int e=ccci_tetris_owner_start(&modem);
        assert(e<0 && calls==fault && !wdt_enabled && !release_count);
        assert(ccci_tetris_owner_start(&modem)==e && calls==fault);
    }
    owner_setup();lower_positive=1;assert(ccif_start(CCIF_HIF_ID)==-EPROTO && !ccif_tail && !ccif_irq);
    owner_setup();lower_positive=1;assert(dpmaif_start(DPMAIF_HIF_ID)==-EPROTO && !dpmaif_tail && !dpmaif_irq);
    owner_setup();dpmaif_ctl=NULL;assert(dpmaif_start(DPMAIF_HIF_ID)==-ENODEV && !calls);
    owner_setup();ccci_ccif_ctrl=NULL;assert(ccif_start(CCIF_HIF_ID)==-ENODEV && !calls);
    owner_setup();assert(dpmaif_start(CCIF_HIF_ID)==-ENODEV && !calls);
    owner_setup();assert(ccif_start(DPMAIF_HIF_ID)==-ENODEV && !calls);
    owner_setup();dpmaif_controller.dpmaif_state=DPMAIF_STATE_PWRON;
    assert(dpmaif_start(DPMAIF_HIF_ID)==-EBUSY && !calls);
    owner_setup();ccif_controller.ccif_state=HIFCCIF_STATE_PWRON;
    assert(ccif_start(CCIF_HIF_ID)==-EBUSY && !calls);
    owner_setup();
    puts("Owner/real backend/provider: gated WDT/CCIF/DPMAIF/HS1 order, every external first fault, clock failures and no retry PASS");
}
'''


def native_ci(kernel, vendor):
    with tempfile.TemporaryDirectory(prefix="tetris-owner-native-") as temp:
        out = Path(temp)
        prepare_vendor(vendor, out)
        power = first.power
        power.FILES.update({first.SOURCE, first.PUBLIC, "drivers/soc/mediatek/Kconfig", "drivers/soc/mediatek/Makefile"})
        for name in power.FILES:
            source = kernel / name
            if source.exists():
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, out / name)
        patches = re.findall(r"^\s+([\w.-]+\.patch)$", (power.PACKAGE / "APKBUILD").read_text(), re.M)
        for name in dict.fromkeys(patches + [power.PATCH.name, first.PATCH]):
            selected = "".join(power.sections((power.PACKAGE / name).read_text(encoding="latin-1")))
            if selected:
                apply_patch(out, selected)
        native = out / "native"
        native.mkdir()
        for source, name in [(first.SOURCE, "mt6878-ccci-start.c"), (first.PUBLIC, "mt6878_ccci_start.h")]:
            text = re.sub(r"^#include <linux/[^\n]+>\n", "", (out / source).read_text(), flags=re.M)
            (native / name).write_text(text)
        shutil.copyfile(out / "drivers/pmdomain/mediatek/mt6878-modem-pm.h", native / "mt6878-modem-pm.h")
        for name, source in NEW.items():
            text = re.sub(r"^#include [^\n]+\n", "", source.read_text(), flags=re.M)
            (native / Path(name).name).write_text(text)
        funcs = [("fsm/modem_sys1.c", "ccci_tetris_wdt_init_owned", "wdt.c"),
                 ("fsm/ccci_fsm.c", "ccci_tetris_publish_hs1", "hs1.c"),
                 ("hif/ccci_hif_ccif.c", "ccif_owner_clocks", "ccif-clocks.c"),
                 ("hif/ccci_dpmaif_com.c", "dpmaif_owner_clocks", "dpmaif-clocks.c"),
                 ("hif/ccci_hif_ccif.c", "ccif_start", "ccif-start.c"),
                 ("hif/ccci_hif_ccif.c", "ccif_enable_irq1", "ccif-irq.c"),
                 ("hif/ccci_dpmaif_com.c", "dpmaif_start", "dpmaif-start.c")]
        for source, func, dest in funcs:
            (native / dest).write_text(function((out / PREFIX / source).read_text(), func) + "\n")
        harness = first.HARNESS.split("int main(void){", 1)[0]
        harness = harness.replace("struct device {", 'struct bus_type {const char *name;};\nstruct device {struct bus_type *bus;')
        (native / "test.c").write_text(harness + EXTRA)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", str(native / "test.c"),
                        "-o", str(native / "test")], check=True)
        subprocess.run([str(native / "test")], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor", type=Path)
    parser.add_argument("--emit-bundle", type=Path, help="write a generated self-contained vendor patch")
    parser.add_argument("--native-ci", type=Path, metavar="PRISTINE_KERNEL")
    args = parser.parse_args()
    if args.native_ci and os.environ.get("CI") != "true":
        parser.error("native C compilation is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-owner-apply-") as temp:
        prepare_vendor(args.vendor, Path(temp))
    if args.emit_bundle:
        args.emit_bundle.write_text(bundle())
    if args.native_ci:
        native_ci(args.native_ci, args.vendor)


if __name__ == "__main__":
    main()
