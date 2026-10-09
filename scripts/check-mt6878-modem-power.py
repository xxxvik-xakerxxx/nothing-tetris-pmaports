#!/usr/bin/env python3
"""Apply the modem patch to a pinned kernel; optional native tests are CI-only."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
PATCH = PACKAGE / "0113-pmdomain-mediatek-mt6878-modem-power.patch"
FILES = {
    "drivers/pmdomain/mediatek/mtk-pm-domains.c",
    "drivers/pmdomain/mediatek/mtk-pm-domains.h",
    "drivers/pmdomain/mediatek/mt6878-modem-pm.h",
    "Documentation/devicetree/bindings/power/mediatek,power-controller.yaml",
}


def sections(text):
    headers = list(re.finditer(r"^--- (?:a/\S+|/dev/null)\n\+\+\+ b/(\S+)\n", text, re.M))
    for index, match in enumerate(headers):
        if match[1] not in FILES:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        section = text[match.start():end].split("\ndiff --git ")[0]
        yield section.split("\n-- \n")[0] + "\n"


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
typedef uint32_t u32;
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((UINT32_MAX << (l)) & (UINT32_MAX >> (31 - (h))))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define MTK_SCPD_MT6878_MD BIT(15)
#define MTK_SCPD_KEEP_DEFAULT_OFF BIT(3)
#define MTK_SCPD_STATUS_IN_CTL BIT(12)
#define MTK_SCPD_SKIP_RESET_B BIT(11)
#define PWR_ON_BIT BIT(2)
#define MTK_POLL_DELAY_US 10
#define MTK_POLL_TIMEOUT 1000000
enum scpsys_bus_prot_block { BUS_PROT_BLOCK_INFRA, BUS_PROT_BLOCK_NEMICFG };
struct scpsys_bus_prot_data { int bus_prot_block; u32 bus_prot_set_clr_mask;
    u32 bus_prot_set, bus_prot_clr, bus_prot_sta_mask, bus_prot_sta; };
#define BUS_PROT_WR(b,m,s,c,a) {BUS_PROT_BLOCK_##b,m,s,c,m,a}
struct scpsys_domain_data { const char *name; u32 sta_mask, ctl_offs;
    u32 pwr_sta_offs, pwr_sta2nd_offs, caps;
    struct scpsys_bus_prot_data bp_cfg[3]; };
struct scpsys_soc_data { const struct scpsys_domain_data *domains_data;
    int num_domains; enum scpsys_bus_prot_block *bus_prot_blocks;
    int num_bus_prot_blocks; };
struct regmap { u32 words[1024]; int id; };
struct scpsys { struct regmap *base, *maps[2]; void *dev; };
struct generic_pm_domain { int unused; };
struct scpsys_domain { struct generic_pm_domain genpd;
    struct scpsys *scpsys; const struct scpsys_domain_data *data;
    int md_error; bool md_owned; };
#define to_scpsys_domain(g) ((struct scpsys_domain *)(g))
#define dev_err(...) ((void)0)
static int calls, fail_at, stuck;
struct event { int id, op; u32 offset, mask; };
static struct event trace[256];
static int record(struct regmap *m, int op, u32 off, u32 mask) {
    assert(calls < 256);
    trace[calls++] = (struct event){m->id,op,off,mask};
    return calls == fail_at ? -EIO : 0;
}
static int regmap_read(struct regmap *m,u32 off,u32 *v) {
    int e=record(m,0,off,0); if(e)return e; *v=m->words[off/4]; return 0;
}
static int update(struct regmap *m,u32 off,u32 mask,bool set) {
    int e=record(m,set?1:2,off,mask); if(e)return e;
    if(set)m->words[off/4]|=mask; else m->words[off/4]&=~mask;
    if(off==0xe00 && stuck!=-1 && stuck!=calls) {
        m->words[off/4]&=~GENMASK(31,30);
        if(m->words[off/4]&BIT(2))m->words[off/4]|=GENMASK(31,30);
    }
    return 0;
}
static int regmap_set_bits(struct regmap *m,u32 o,u32 b){return update(m,o,b,true);}
static int regmap_clear_bits(struct regmap *m,u32 o,u32 b){return update(m,o,b,false);}
static int regmap_write(struct regmap *m,u32 off,u32 mask) {
    int e=record(m,3,off,mask); if(e)return e;
    u32 status= off==0xc54 || off==0xc58 ? 0xc5c :
                off==0xc44 || off==0xc48 ? 0xc4c : 0x8c;
    bool set=off==0xc54 || off==0xc44 || off==0x84;
    if(stuck!=-1 && stuck!=calls) {
        if(set)m->words[status/4]|=mask; else m->words[status/4]&=~mask;
    }
    return 0;
}
#define regmap_read_poll_timeout(m,o,v,cond,d,t) \
    ({ int e=regmap_read(m,o,&v); e ? e : ((cond) ? 0 : -ETIMEDOUT); })
static struct regmap *scpsys_bus_protect_get_regmap(struct scpsys_domain *p,
    const struct scpsys_bus_prot_data *b){return p->scpsys->maps[b->bus_prot_block];}
#include "mt6878-modem-pm.h"
static struct regmap base, infra, nemi;
static struct scpsys scp;
static struct scpsys_domain pd;
static void setup(void) {
    base=(struct regmap){.id=0}; infra=(struct regmap){.id=1};
    nemi=(struct regmap){.id=2};
    base.words[0xe00/4]=BIT(0); base.words[0xf24/4]=3;
    infra.words[0xc5c/4]=BIT(9); infra.words[0xc4c/4]=BIT(11);
    nemi.words[0x8c/4]=BIT(6)|BIT(7);
    scp=(struct scpsys){.base=&base,.maps={&infra,&nemi}};
    pd=(struct scpsys_domain){.scpsys=&scp,.data=&mt6878_md_domains[0]};
    calls=0; fail_at=0; stuck=0;
}
static void unchanged_reset(void) {
    assert(base.words[0xe00/4]&BIT(0));
    assert(!(base.words[0xe00/4]&BIT(3)));
    for(int i=0;i<calls;i++)if(trace[i].id==0 && trace[i].op)
        assert(trace[i].mask==(trace[i].offset==0xe00?BIT(2):3));
}
int main(void) {
    setup(); assert(mt6878_md_scpsys_data.num_domains==1);
    assert(mt6878_md_check_off(&pd)==0); assert(calls==5);
    for(int i=1;i<=5;i++) {
        setup();fail_at=i;assert(mt6878_md_check_off(&pd)==-EIO);assert(calls==i);
    }
    for(unsigned i=0;i<3;i++) {
        setup();base.words[0xe00/4]|= i==0?BIT(2):BIT(29+i);
        assert(mt6878_md_check_off(&pd)==-EBUSY);assert(calls==1);
    }
    setup();base.words[0xf24/4]=0;assert(mt6878_md_check_off(&pd)==-EBUSY);
    setup();infra.words[0xc5c/4]=0;assert(mt6878_md_check_off(&pd)==-EBUSY);
    setup();assert(mt6878_md_power_on(&pd.genpd)==0);assert(pd.md_owned);
    int on_calls=calls; assert(on_calls==14);
    assert(trace[5].offset==0xf24 && trace[5].op==2);
    assert(trace[6].offset==0xe00 && trace[6].op==1);
    assert(trace[8].offset==0x88 && trace[10].offset==0xc48 && trace[12].offset==0xc58);
    unchanged_reset();calls=0;
    assert(mt6878_md_power_off(&pd.genpd)==0);assert(!pd.md_owned);
    int off_calls=calls;assert(off_calls==9);
    assert(trace[0].offset==0xc54 && trace[2].offset==0xc44 && trace[4].offset==0x84);
    assert(trace[6].offset==0xe00 && trace[6].op==2);
    assert(trace[7].offset==0xe00 && trace[7].op==0);
    assert(trace[8].offset==0xf24 && trace[8].op==1);
    unchanged_reset();assert(mt6878_md_check_off(&pd)==0);
    for(int f=1;f<=on_calls;f++) {
        setup();fail_at=f;assert(mt6878_md_power_on(&pd.genpd)==-EIO);
        assert(calls==f && pd.md_error==-EIO);
        assert(mt6878_md_power_on(&pd.genpd)==-EIO);
        assert(mt6878_md_power_off(&pd.genpd)==-EIO);assert(calls==f);unchanged_reset();
    }
    for(int f=1;f<=off_calls;f++) {
        setup();assert(mt6878_md_power_on(&pd.genpd)==0);calls=0;fail_at=f;
        assert(mt6878_md_power_off(&pd.genpd)==-EIO);assert(calls==f && pd.md_error==-EIO);
        assert(mt6878_md_power_off(&pd.genpd)==-EIO);assert(calls==f);unchanged_reset();
    }
    int on_stalls[]={7,9,11,13}, off_stalls[]={1,3,5,7};
    for(unsigned i=0;i<ARRAY_SIZE(on_stalls);i++) {
        setup();stuck=on_stalls[i];
        assert(mt6878_md_power_on(&pd.genpd)==-ETIMEDOUT);
        assert(calls==stuck+1 && pd.md_error==-ETIMEDOUT);
        assert(mt6878_md_power_on(&pd.genpd)==-ETIMEDOUT);
        assert(calls==stuck+1);unchanged_reset();
    }
    for(unsigned i=0;i<ARRAY_SIZE(off_stalls);i++) {
        setup();assert(mt6878_md_power_on(&pd.genpd)==0);calls=0;stuck=off_stalls[i];
        assert(mt6878_md_power_off(&pd.genpd)==-ETIMEDOUT);
        assert(calls==stuck+1 && pd.md_error==-ETIMEDOUT);
        assert(mt6878_md_power_off(&pd.genpd)==-ETIMEDOUT);
        assert(calls==stuck+1);unchanged_reset();
    }
    setup();mt6878_md_cleanup(&pd);assert(calls==0);
    setup();base.words[0xe00/4]|=GENMASK(31,30);
    mt6878_md_cleanup(&pd);assert(calls==0);
    setup();assert(mt6878_md_power_on(&pd.genpd)==0);calls=0;
    mt6878_md_cleanup(&pd);assert(calls==off_calls && !pd.md_owned);
    setup();assert(mt6878_md_power_on(&pd.genpd)==0);calls=0;fail_at=1;
    mt6878_md_cleanup(&pd);assert(calls==1 && pd.md_error==-EIO);
    mt6878_md_cleanup(&pd);assert(calls==1);
    puts("MT6878 modem sequence: success, inherited state, every I/O fault, timeout and latch PASS");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, help="unpatched pinned Linux source")
    parser.add_argument("--native-ci", action="store_true")
    args = parser.parse_args()
    if args.native_ci and os.environ.get("CI") != "true":
        parser.error("native C builds are allowed only with CI=true in CI")
    with tempfile.TemporaryDirectory(prefix="tetris-md-power-") as directory:
        out = Path(directory)
        for name in FILES:
            source = args.kernel / name
            if source.exists():
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        names = re.findall(r"^\s+([\w.-]+\.patch)$", (PACKAGE / "APKBUILD").read_text(), re.M)
        for name in dict.fromkeys(names + [PATCH.name]):
            text = "".join(sections((PACKAGE / name).read_text(encoding="latin-1")))
            if text:
                print(f"Applying {name}", flush=True)
                subprocess.run(["git", "apply", "--unsafe-paths", "-"], cwd=out,
                               input=text, text=True, check=True)
        header = out / "drivers/pmdomain/mediatek/mt6878-modem-pm.h"
        source = header.read_text()
        assert "PWR_RST_B_BIT" not in source and "PWR_ON_2ND_BIT" not in source
        controller = (out / "drivers/pmdomain/mediatek/mtk-pm-domains.c").read_text()
        assert "mt6878_md_check_off(pd)" in controller
        cleanup = controller.split("static void scpsys_remove_one_domain", 1)[1].split(
            "static void scpsys_domain_cleanup", 1)[0]
        assert "mt6878_md_cleanup(pd)" in cleanup
        assert "scpsys_power_off(&pd->genpd)" not in cleanup
        print("Modem patch applies after packaged scpsys patches; no DT enabling")
        if args.native_ci:
            # Generated native fixture is intentionally confined to CI scratch.
            (header.parent / "modem-test.c").write_text(HARNESS)
            subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
                            "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                            str(header.parent / "modem-test.c"), "-o", str(out / "modem-test")], check=True)
            subprocess.run([str(out / "modem-test")], check=True)


if __name__ == "__main__":
    main()
