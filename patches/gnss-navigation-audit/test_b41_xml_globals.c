/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_xml_globals.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libxml/parser.h>
#include <openssl/evp.h>
static unsigned xml_reads, digest_calls;
static uint8_t *mutate_xml;
extern xmlDocPtr __real_xmlReadMemory(const char *, int, const char *, const char *, int);
extern int __real_EVP_Digest(const void *, size_t, unsigned char *, unsigned int *,
    const EVP_MD *, ENGINE *);
xmlDocPtr __wrap_xmlReadMemory(const char *data, int size, const char *url,
    const char *encoding, int options)
{
    ++xml_reads;
    return __real_xmlReadMemory(data, size, url, encoding, options);
}
int __wrap_EVP_Digest(const void *data, size_t size, unsigned char *out,
    unsigned int *written, const EVP_MD *md, ENGINE *engine)
{
    ++digest_calls;
    int status = __real_EVP_Digest(data, size, out, written, md, engine);
    if (mutate_xml) { *mutate_xml ^= 1; mutate_xml = NULL; }
    return status;
}
static void *load(const char *path, size_t *length)
{
    FILE *file = fopen(path, "rb"); assert(file);
    assert(!fseek(file, 0, SEEK_END)); long size = ftell(file);
    assert(size > 0 && size < 16 * 1024 * 1024); rewind(file);
    void *data = malloc((size_t)size); assert(data);
    assert(fread(data, 1, (size_t)size, file) == (size_t)size);
    assert(!fclose(file)); *length = (size_t)size; return data;
}
int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    size_t elf_size, xml_size;
    void *elf = load(argv[1], &elf_size), *xml = load(argv[2], &xml_size);
    size_t extent = B41_XML_GLOBAL_VADDR + B41_XML_GLOBAL_SIZE;
    uint8_t *image = calloc(1, extent); assert(image);
    uintptr_t target = (uintptr_t)(image + B41_XML_GLOBAL_VADDR);
    /* Synthetic mapped image is a host fixture, never a loaded/running engine. */
    memcpy(image + B41_XML_GLOBAL_GOT, &target, 8);
    uintptr_t chip_target = (uintptr_t)(image + B41_XML_CHIP_VADDR);
    memcpy(image + B41_XML_CHIP_GOT, &chip_target, 8);
    uint32_t chip = argc == 5 ? (uint32_t)strtoul(argv[4], NULL, 10) : 6637;
    memcpy((void *)chip_target, &chip, 4);
    memset((void *)target, 0xa5, B41_XML_GLOBAL_SIZE);
    struct b41_xml_global_owner owner = {0};
    assert(b41_xml_global_owner_bind(&owner, elf, elf_size, image, extent - 1) == -ERANGE);
    ((uint8_t *)elf)[0] ^= 1;
    assert(b41_xml_global_owner_bind(&owner, elf, elf_size, image, extent) == -EKEYREJECTED);
    ((uint8_t *)elf)[0] ^= 1;
    assert(b41_xml_global_owner_bind(&owner, elf, elf_size, image, extent) == 0);
    assert(b41_xml_global_owner_bind(&owner, elf, elf_size, image, extent) == -EALREADY);
    assert(b41_xml_global_owner_apply(&owner, xml, xml_size, argv[3]) == 0);
    assert(owner.applied_features == 1);
    uint8_t before[B41_XML_GLOBAL_SIZE]; memcpy(before, (void *)target, sizeof(before));
    uint8_t initial[B41_XML_GLOBAL_SIZE]; memset(initial, 0xa5, sizeof(initial));
    struct b41_xml_feature applied_feature;
    struct b41_xml_global_patch applied;
    struct b41_xml_set_inputs inputs = {1, chip};
    assert(b41_xml_config_get(xml, xml_size, argv[3], &applied_feature) == 1);
    assert(b41_xml_global_plan(&applied_feature, initial, &inputs, &applied) == 0);
    assert(memcmp(before, applied.bytes, sizeof(before)) == 0);
    assert(b41_xml_global_owner_expose(&owner) == 0);
    assert(b41_xml_global_owner_apply(&owner, xml, xml_size, argv[3]) == -EPERM);
    assert(memcmp(before, (void *)target, sizeof(before)) == 0);
    struct b41_xml_global_owner fault = {0};
    assert(b41_xml_global_owner_bind(&fault, elf, elf_size, image, extent) == 0);
    uint32_t unknown = 0; memcpy((void *)chip_target, &unknown, 4);
    assert(b41_xml_global_owner_apply(&fault, xml, xml_size, "DCB") == -ENODEV);
    memcpy((void *)chip_target, &chip, 4);
    assert(b41_xml_global_owner_apply(&fault, xml, xml_size, argv[3]) == -ENODEV);
    assert(memcmp(before, (void *)target, sizeof(before)) == 0);
    struct b41_xml_global_owner stale = {0};
    assert(b41_xml_global_owner_bind(&stale, elf, elf_size, image, extent) == 0);
    uintptr_t changed = target + 8; memcpy(image + B41_XML_GLOBAL_GOT, &changed, 8);
    assert(b41_xml_global_owner_apply(&stale, xml, xml_size, argv[3]) == -ESTALE);
    memcpy(image + B41_XML_GLOBAL_GOT, &target, 8);
    assert(b41_xml_global_owner_apply(&stale, xml, xml_size, argv[3]) == -ESTALE);
    assert(memcmp(before, (void *)target, sizeof(before)) == 0);
    struct b41_xml_feature feature;
    struct b41_xml_global_patch patch, untouched;
    memset(&patch, 0x5a, sizeof(patch)); untouched = patch;
    assert(b41_xml_config_get(xml, xml_size, "L5Test", &feature) == 1);
    assert(b41_xml_global_plan(&feature, before, NULL, &patch) == -EACCES);
    assert(memcmp(&patch, &untouched, sizeof(patch)) == 0);
    assert(b41_xml_config_get(xml, xml_size, "SignalConfig", &feature) == 1);
    feature.bytes[0x2c] = 1; /* Nonzero unused setting cannot become a default. */
    assert(b41_xml_global_plan(&feature, before, NULL, &patch) == -ENODATA);
    assert(memcmp(&patch, &untouched, sizeof(patch)) == 0);
    assert(b41_xml_config_get(xml, xml_size, "DisableSignal", &feature) == 1);
    memset(feature.bytes + 0x24, 0xff, 8); /* NaN: no guessed FCVT result. */
    assert(b41_xml_global_plan(&feature, before, NULL, &patch) == -ERANGE);
    assert(memcmp(&patch, &untouched, sizeof(patch)) == 0);
    assert(b41_xml_config_get(xml, xml_size, "DCB", &feature) == 1);
    assert(b41_xml_global_plan(&feature, before, NULL, &patch) == -ENODATA);
    assert(memcmp(&patch, &untouched, sizeof(patch)) == 0);
    struct b41_xml_global_owner bad_xml = {0};
    assert(b41_xml_global_owner_bind(&bad_xml, elf, elf_size, image, extent) == 0);
    ((uint8_t *)xml)[0] ^= 1;
    assert(b41_xml_global_owner_apply(&bad_xml, xml, xml_size, argv[3]) < 0);
    int error = bad_xml.first_error;
    ((uint8_t *)xml)[0] ^= 1;
    assert(b41_xml_global_owner_apply(&bad_xml, xml, xml_size, argv[3]) == error);
    assert(memcmp(before, (void *)target, sizeof(before)) == 0);
    struct b41_xml_stock_receipt receipt, receipt_before;
    memset(&receipt, 0x5a, sizeof(receipt)); receipt_before = receipt;
    struct b41_xml_global_owner stock_fault = {0}, stock = {0};
    memcpy((void *)target, initial, sizeof(initial));
    assert(!b41_xml_global_owner_bind(&stock_fault, elf, elf_size, image, extent));
    memcpy((void *)chip_target, &unknown, 4);
    assert(b41_xml_global_owner_apply_stock(&stock_fault, xml, xml_size, &receipt) == -ENODEV);
    assert(!memcmp((void *)target, initial, sizeof(initial)));
    assert(!memcmp(&receipt, &receipt_before, sizeof(receipt)));
    memcpy((void *)chip_target, &chip, 4);
    assert(b41_xml_global_owner_apply_stock(&stock_fault, xml, xml_size, &receipt) == -ENODEV);
    assert(!b41_xml_global_owner_bind(&stock, elf, elf_size, image, extent));
    xml_reads = digest_calls = 0;
    assert(!b41_xml_global_owner_apply_stock(&stock, xml, xml_size, &receipt));
    assert(xml_reads == 1 && digest_calls == 1);
    const uint32_t disabled = (1u << 4) | (1u << 7) | (1u << 12) | (1u << 15);
    assert(receipt.disabled == disabled && receipt.enabled == ((1u << 19) - 1u - disabled));
    assert(receipt.committed_features == 15 && stock.applied_features == 15 && stock.stock_applied);
    const char *const names[] = {"IFB", "GGTO", "DCB", "L1Only", "L5Test", "DisableSignal", "GLP",
        "CAIC", "GnssMode", "Bluesky", "CoTMS", "SwitchTIA", "Blanking", "MDTime", "Time_Source",
        "PSO", "GNSSPower", "OSNMA", "SignalConfig"};
    uint8_t expected[B41_XML_GLOBAL_SIZE], written[B41_XML_GLOBAL_SIZE] = {0};
    memcpy(expected, initial, sizeof(expected));
    for (unsigned i = 0; i < 19; ++i) {
        assert(b41_xml_config_get(xml, xml_size, names[i], &feature) == 1);
        if (!feature.bytes[0x1c]) continue;
        assert(!b41_xml_global_plan(&feature, expected, &inputs, &patch));
        memcpy(expected, patch.bytes, sizeof(expected));
        for (unsigned byte = 0; byte < sizeof(written); ++byte) written[byte] |= patch.written[byte];
    }
    assert(!memcmp((void *)target, expected, sizeof(expected)));
    assert(!memcmp(receipt.written, written, sizeof(written)));
    for (unsigned byte = 0; byte < sizeof(written); ++byte)
        if (!written[byte]) assert(expected[byte] == initial[byte]);
    assert(b41_xml_global_owner_apply_stock(&stock, xml, xml_size, &receipt) == -EALREADY);
    assert(b41_xml_global_owner_apply(&stock, xml, xml_size, "GLP") == -EALREADY);
    assert(!b41_xml_global_owner_expose(&stock));
    assert(b41_xml_global_owner_apply_stock(&stock, xml, xml_size, &receipt) == -EPERM);
    struct b41_xml_feature decoded[2], decoded_before[2];
    memset(decoded, 0x5a, sizeof(decoded)); memcpy(decoded_before, decoded, sizeof(decoded));
    const char *const missing[] = {"IFB", "missing"};
    assert(b41_xml_config_get_many(xml, xml_size, missing, 2, decoded) == -ENOENT);
    assert(!memcmp(decoded, decoded_before, sizeof(decoded)));
    const char *const null_name[] = {"IFB", NULL};
    assert(b41_xml_config_get_many(xml, xml_size, null_name, 2, decoded) == -EINVAL);
    assert(!memcmp(decoded, decoded_before, sizeof(decoded)));
    assert(b41_xml_config_get_many(xml, xml_size, names, 0, decoded) == -EINVAL);
    assert(b41_xml_config_get_many(xml, xml_size, names, 20, decoded) == -EINVAL);
    assert(!memcmp(decoded, decoded_before, sizeof(decoded)));
    xml_reads = digest_calls = 0;
    ((uint8_t *)xml)[0] ^= 1;
    assert(b41_xml_config_get_many(xml, xml_size, names, 2, decoded) == -EBADMSG);
    assert(xml_reads == 0 && digest_calls == 1);
    ((uint8_t *)xml)[0] ^= 1;
    assert(!memcmp(decoded, decoded_before, sizeof(decoded)));
    mutate_xml = xml;
    assert(b41_xml_config_get_many(xml, xml_size, names, 2, decoded) == 1);
    ((uint8_t *)xml)[0] ^= 1;
    assert(b41_xml_config_get(xml, xml_size, names[0], &feature) == 1);
    assert(!memcmp(decoded, &feature, sizeof(feature)));
    assert(b41_xml_config_get(xml, xml_size, names[1], &feature) == 1);
    assert(!memcmp(decoded + 1, &feature, sizeof(feature)));
    /* Keep original single-feature output protocol for the exact consumer oracle. */
    assert(fwrite(before, 1, sizeof(before), stdout) == sizeof(before));
    assert(fwrite(applied.written, 1, sizeof(applied.written), stdout) == sizeof(applied.written));
    free(image); free(xml); free(elf);
    return 0;
}
