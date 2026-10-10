/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_xml_set_tail.h"
#include <assert.h>
#include <errno.h>
#include <fenv.h>
#include <locale.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void put_number(struct b41_xml_feature *f, unsigned offset, double value)
{
    uint64_t bits;
    memcpy(&bits, &value, 8);
    for (unsigned i = 0; i < 8; ++i) f->bytes[offset + i] = (uint8_t)(bits >> (8 * i));
}

static struct b41_xml_feature fixture(const char *name, double version, unsigned count)
{
    struct b41_xml_feature f = {{0}};
    assert(strlen(name) < 20);
    strcpy((char *)f.bytes, name);
    put_number(&f, 0x14, version);
    f.bytes[0x1c] = 1;
    for (unsigned i = 0; i < 4; ++i) f.bytes[0x20 + i] = (uint8_t)(count >> (8 * i));
    return f;
}

static void wire(const struct b41_xml_set_message *out, const char *body)
{
    char expected[B41_XML_SET_WIRE_CAPACITY];
    unsigned checksum = 0;
    for (size_t i = 0; body[i]; ++i) checksum ^= (uint8_t)body[i];
    int n = snprintf(expected, sizeof(expected), "$%s*%02X\r\n", body, checksum);
    assert(n > 0 && out->length == (unsigned)n);
    assert(!memcmp(out->bytes, expected, (size_t)n + 1));
}

static void refused(const struct b41_xml_feature *f, int expected)
{
    struct b41_xml_set_message out, before;
    memset(&out, 0xa5, sizeof(out)); before = out;
    assert(b41_xml_set_serialize(f, &out) == expected);
    assert(!memcmp(&out, &before, sizeof(out)));
}

int main(int argc, char **argv)
{
    assert(setlocale(LC_NUMERIC, "C"));
    assert(!fesetround(FE_TONEAREST));
    struct b41_xml_set_message out;
    struct b41_xml_feature f = fixture("CoTMS", 5, 3);
    put_number(&f, 0x24, 3); put_number(&f, 0x2c, 4); put_number(&f, 0x34, 1);
    assert(!b41_xml_set_serialize(&f, &out) && out.emitted_settings == 3);
    wire(&out, "XML:CoTMS,v5.00,Cfg,3,4,1");
    f = fixture("GGTO", 1, 4);
    put_number(&f, 0x24, 11.97); put_number(&f, 0x2c, 0.87);
    put_number(&f, 0x34, 2.94); put_number(&f, 0x3c, 13.62);
    assert(!b41_xml_set_serialize(&f, &out));
    wire(&out, "XML:GGTO,v1.00,Cfg,11.970000,0.870000,2.940000,13.620000");
    f = fixture("DCB", 1, 3);
    put_number(&f, 0x24, 1e-8); put_number(&f, 0x2c, -0.0); put_number(&f, 0x34, -8.16);
    assert(!b41_xml_set_serialize(&f, &out) && out.emitted_settings == 1);
    wire(&out, "XML:DCB,v1.00,Cfg,-8.160000");
    f = fixture("DisableSignal", 1, 1);
    assert(!b41_xml_set_serialize(&f, &out)); wire(&out, "XML:DisableSignal,v1.00,Cfg,0");
    put_number(&f, 0x2c, 1e-8); refused(&f, -ERANGE); /* Count exhaustion is not generalized. */
    put_number(&f, 0x2c, 0);
    f.bytes[0x1c] = 0; refused(&f, -EACCES); f.bytes[0x1c] = 1;
    put_number(&f, 0x14, 9); refused(&f, -ENOTSUP); put_number(&f, 0x14, 1);
    put_number(&f, 0x24, NAN); refused(&f, -ERANGE); put_number(&f, 0x24, 0);
    f.bytes[0x20] = 128; refused(&f, -ERANGE);
    f = fixture("CoTMS", 5, 100);
    for (unsigned i = 0; i < 100; ++i) put_number(&f, 0x24 + i * 8, 1e100);
    refused(&f, -ENOSPC);
    f = fixture("L5Test", 1, 1); refused(&f, -ENOTSUP);
    refused(NULL, -EINVAL);
    f = fixture("DisableSignal", 1, 127);
    assert(!b41_xml_set_serialize(&f, &out) && out.emitted_settings == 127);
    assert(out.length < B41_XML_SET_WIRE_CAPACITY && !out.bytes[out.length]);
    f = fixture("DisableSignal", 1, 1);
    put_number(&f, 0xfc4 - 8, 1e-8); refused(&f, -ERANGE);
    put_number(&f, 0xfc4 - 8, NAN); refused(&f, -ERANGE);
    f = fixture("DisableSignal", 1, 0); refused(&f, -ERANGE);
    f = fixture("DisableSignal", 1, 1);
    f.bytes[0x1c] = 2; refused(&f, -EINVAL);
    memset(f.bytes, 'x', 20); refused(&f, -EINVAL);
    f = fixture("GLP", 2, 1);
    assert(!fesetround(FE_DOWNWARD)); refused(&f, -ENOTSUP); assert(!fesetround(FE_TONEAREST));
    if (argc == 2) {
        FILE *file = fopen(argv[1], "rb"); assert(file);
        assert(fread(&f, 1, sizeof(f), file) == sizeof(f));
        assert(fgetc(file) == EOF && !ferror(file)); assert(!fclose(file));
        assert(!b41_xml_set_serialize(&f, &out));
        assert(fwrite(out.bytes, 1, out.length, stdout) == out.length);
    } else assert(argc == 1);
    return 0;
}
