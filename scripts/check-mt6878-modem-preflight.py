#!/usr/bin/env python3
"""Check the exact read-only diagnostic; execute native fault tests only in CI."""
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
spec = importlib.util.spec_from_file_location(
    "modem_power_check", Path(__file__).with_name("check-mt6878-modem-power.py"))
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
PATCH = power.PACKAGE / "0115-pmdomain-mediatek-mt6878-read-only-modem-preflight.patch"
HEADER = "drivers/pmdomain/mediatek/mt6878-modem-preflight.h"
SCHEMA = "Documentation/devicetree/bindings/power/mediatek,mt6878-modem-preflight.yaml"
FIXTURE = "arch/arm64/boot/dts/mediatek/mt6878-disabled-modem-preflight.dtsi"

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdarg.h>
typedef uint32_t u32;
typedef uint64_t resource_size_t;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(a[0]))
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((UINT32_MAX << (l)) & (UINT32_MAX >> (31-(h))))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
typedef struct {int counter;} atomic_t;
#define ATOMIC_INIT(v) {v}
static int atomic_cmpxchg(atomic_t *a,int old,int new_value) {
    int v=a->counter;if(v==old)a->counter=new_value;return v;
}
struct resource {resource_size_t start,end;};
static resource_size_t resource_size(const struct resource *r){return r->end-r->start+1;}
struct regmap {int id;};
struct device_node { const char *compatible;resource_size_t start,size;
    bool extra,syscon;unsigned props;int references; };
struct device {struct device *parent;struct device_node *of_node;};
struct platform_device {struct device dev;};
static struct device_node parent_node,ifr_node,nemi_node,np_node,child_node;
static struct device parent_device;
static struct platform_device pdev;
static struct regmap maps[3];
static bool has_child;
static int handles,read_count,fail_read,map_count,fail_map,begin_count,done_count;
static u32 supplied[5],actual_offsets[5];
static int actual_maps[5];
static char last_log[512];
static int log_message(const char *fmt,...) {
    va_list ap;va_start(ap,fmt);vsnprintf(last_log,sizeof(last_log),fmt,ap);va_end(ap);
    if(strstr(fmt,"read-begin"))begin_count++;
    if(strstr(fmt,"read-done"))done_count++;
    return 0;
}
#define dev_info(dev,...) ((void)(dev),log_message(__VA_ARGS__))
#define dev_err(dev,...) ((void)(dev),log_message(__VA_ARGS__))
#define dev_err_probe(dev,e,...) ((void)(dev),log_message(__VA_ARGS__),(e))
static bool of_device_is_compatible(struct device_node *n,const char *s) {
    return n && (!strcmp(s,"syscon") ? n->syscon : !strcmp(n->compatible,s));
}
static bool of_property_present(struct device_node *n,const char *s) {
    unsigned bit=!strcmp(s,"clocks")?1:!strcmp(s,"resets")?2:
        !strcmp(s,"hwlocks")?4:!strcmp(s,"power-domains")?8:
        !strcmp(s,"#power-domain-cells")?16:0;
    return n && (n->props&bit);
}
static int of_address_to_resource(struct device_node *n,int index,struct resource *r) {
    if(!n || !n->size || (index && !n->extra))return -EINVAL;
    r->start=n->start;r->end=n->start+n->size-1;return 0;
}
static int of_count_phandle_with_args(struct device_node *n,const char *p,const char *c) {
    (void)n;(void)p;(void)c;return handles;
}
static struct device_node *of_parse_phandle(struct device_node *n,const char *s,int i) {
    (void)n;(void)s;struct device_node *result=i?&nemi_node:&ifr_node;
    result->references++;return result;
}
static void of_node_put(struct device_node *n){if(n){assert(n->references>0);n->references--;}}
#define for_each_available_child_of_node(np,child) \
    for((void)(np),(child)=has_child?&child_node:NULL;child;child=NULL)
static struct regmap *get_map(struct device_node *n) {
    map_count++;if(map_count==fail_map)return (struct regmap *)(intptr_t)-EIO;
    return &maps[n==&parent_node?0:n==&ifr_node?1:2];
}
static struct regmap *syscon_node_to_regmap(struct device_node *n){return get_map(n);}
static struct regmap *device_node_to_regmap(struct device_node *n){return get_map(n);}
static int regmap_read(struct regmap *m,u32 off,u32 *value) {
    assert(read_count<5);actual_offsets[read_count]=off;actual_maps[read_count]=m->id;
    read_count++;if(read_count==fail_read)return -EIO;
    *value=supplied[read_count-1];return 0;
}
/* No register-write, genpd, clock, reset, power-on or cleanup stubs exist. */
#include "mt6878-modem-preflight.h"
static void setup(void) {
    mt6878_md_preflight_attempted.counter=0;
    parent_node=(struct device_node){.compatible="mediatek,mt6878-scpsys",
        .start=0x1c001000,.size=0x1000,.syscon=true};
    ifr_node=(struct device_node){.compatible="mediatek,mt6878-infracfg-ao",
        .start=0x10001000,.size=0x1000,.syscon=true};
    nemi_node=(struct device_node){.compatible="mediatek,mt6878-nemicfg_ao_mem_reg_bus",
        .start=0x10270000,.size=0x1000,.syscon=true};
    np_node=(struct device_node){.compatible="mediatek,mt6878-modem-preflight"};
    parent_device=(struct device){.of_node=&parent_node};
    pdev=(struct platform_device){.dev={.parent=&parent_device,.of_node=&np_node}};
    child_node=(struct device_node){.references=1};has_child=false;handles=2;
    read_count=fail_read=map_count=fail_map=begin_count=done_count=0;
    supplied[0]=BIT(0);supplied[1]=3;supplied[2]=BIT(9);
    supplied[3]=BIT(11);supplied[4]=BIT(6)|BIT(7);
    for(int i=0;i<3;i++)maps[i]=(struct regmap){.id=i};
    last_log[0]=0;
}
static void references_released(void) {
    assert(ifr_node.references==0 && nemi_node.references==0);
}
static void no_second_attempt(void) {
    int maps_before=map_count,reads_before=read_count;
    assert(mt6878_modem_preflight(&pdev)==-EALREADY);
    assert(map_count==maps_before && read_count==reads_before);
}
int main(void) {
    const u32 offsets[]={0xe00,0xf24,0xc5c,0xc4c,0x8c};
    const int map_ids[]={0,0,1,1,2};
    const char *stages[]={"spm-md-power","spm-md-isolation","ifr-md-protect-1",
        "ifr-md-protect-0","nemi-md-protect"};
    setup();assert(mt6878_modem_preflight(&pdev)==0);
    assert(read_count==5 && map_count==3 && begin_count==5 && done_count==5);
    assert(strstr(last_log,"off-isolated-protected=1"));
    for(int i=0;i<5;i++){assert(actual_offsets[i]==offsets[i]);assert(actual_maps[i]==map_ids[i]);}
    references_released();no_second_attempt();
    setup();supplied[0]=GENMASK(31,30)|BIT(2);
    assert(mt6878_modem_preflight(&pdev)==0);assert(read_count==5);
    assert(strstr(last_log,"off-isolated-protected=0"));no_second_attempt();
    for(int i=1;i<=5;i++) {
        setup();fail_read=i;assert(mt6878_modem_preflight(&pdev)==-EIO);
        assert(read_count==i && begin_count==i && done_count==i-1);
        assert(strstr(last_log,stages[i-1]) && strstr(last_log,"first-fault"));
        references_released();no_second_attempt();
    }
    for(int i=1;i<=3;i++) {
        setup();fail_map=i;assert(mt6878_modem_preflight(&pdev)==-EIO);
        assert(map_count==i && read_count==0);references_released();no_second_attempt();
    }
    for(int node=0;node<3;node++)for(int variant=0;variant<7;variant++) {
        setup();struct device_node *n=node==0?&parent_node:node==1?&ifr_node:&nemi_node;
        if(variant==0)n->start+=4;
        if(variant==1)n->size=0x2000;
        if(variant==2)n->extra=true;
        if(variant==3)n->syscon=false;
        if(variant>=4)n->props=1U<<(variant-4);
        assert(mt6878_modem_preflight(&pdev)==-EINVAL);
        assert(read_count==0 && map_count==0);references_released();no_second_attempt();
    }
    setup();has_child=true;assert(mt6878_modem_preflight(&pdev)==-EINVAL);
    assert(read_count==0 && map_count==0 && child_node.references==0);
    for(unsigned props=8;props<=16;props*=2) {
        setup();np_node.props=props;assert(mt6878_modem_preflight(&pdev)==-EINVAL);
        assert(read_count==0 && map_count==0);no_second_attempt();
    }
    setup();handles=1;assert(mt6878_modem_preflight(&pdev)==-EINVAL);
    assert(read_count==0 && map_count==0);no_second_attempt();
    setup();pdev.dev.parent=NULL;assert(mt6878_modem_preflight(&pdev)==-ENODEV);
    assert(read_count==0 && map_count==0);no_second_attempt();
    puts("Read-only modem preflight: exact reads, topology, resource/mapping/read faults and single attempt PASS");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, help="unpatched pinned Linux tree")
    parser.add_argument("--native-ci", action="store_true")
    args = parser.parse_args()
    if args.native_ci and os.environ.get("CI") != "true":
        parser.error("native C compilation is CI-only")
    power.FILES.update({HEADER, SCHEMA, FIXTURE})
    with tempfile.TemporaryDirectory(prefix="tetris-md-preflight-") as directory:
        out = Path(directory)
        for name in power.FILES:
            source = args.kernel / name
            if source.exists():
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        names = re.findall(r"^\s+([\w.-]+\.patch)$", (power.PACKAGE / "APKBUILD").read_text(), re.M)
        for name in dict.fromkeys(names + [power.PATCH.name, PATCH.name]):
            selected = "".join(power.sections((power.PACKAGE / name).read_text(encoding="latin-1")))
            if selected:
                subprocess.run(["git", "apply", "-"], cwd=out, input=selected, text=True, check=True)
        source = (out / HEADER).read_text()
        forbidden = r"\b(?:regmap_(?:write|update_bits|set_bits|clear_bits)|pm_genpd_\w+|scpsys_(?:power|domain_cleanup)\w*|arm_smccc_\w+|clk_\w+|reset_control_\w+)\s*\("
        assert not re.search(forbidden, source), "diagnostic contains mutation API"
        controller = (out / "drivers/pmdomain/mediatek/mtk-pm-domains.c").read_text()
        probe = controller.split("static int scpsys_probe(", 1)[1]
        assert probe.index("return mt6878_modem_preflight(pdev);") < probe.index("of_device_get_match_data")
        fixture = (out / FIXTURE).read_text()
        assert fixture.count('status = "disabled";') == 2
        assert "power-domains" not in fixture and "#power-domain-cells" not in fixture
        print("Read-only preflight applies; early-return/no-mutation/default-disabled checks PASS")
        if args.native_ci:
            native = out / "native"
            (native / "linux").mkdir(parents=True)
            for header in ["atomic.h", "of_address.h"]:
                (native / "linux" / header).write_text("/* Host fixture definitions precede the production header. */\n")
            shutil.copyfile(out / HEADER, native / "mt6878-modem-preflight.h")
            (native / "test.c").write_text(HARNESS)
            subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(native),
                            str(native / "test.c"), "-o", str(native / "test")], check=True)
            subprocess.run([str(native / "test")], check=True)


if __name__ == "__main__":
    main()
