/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_xml_config.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv)
{
    struct b41_xml_feature output, before;
    unsigned char *xml;
    long size;
    assert(argc == 3);
    FILE *file = fopen(argv[1], "rb");
    assert(file);
    assert(fseek(file, 0, SEEK_END) == 0);
    size = ftell(file);
    assert(size > 0 && size <= B41_XML_MAX_SIZE);
    rewind(file);
    xml = malloc((size_t)size);
    assert(xml && fread(xml, 1, (size_t)size, file) == (size_t)size);
    assert(fclose(file) == 0);
    memset(&output, 0xa5, sizeof(output)); before = output;
    assert(b41_xml_config_get(NULL, size, argv[2], &output) == -EINVAL);
    assert(b41_xml_config_get(xml, 0, argv[2], &output) == -EINVAL);
    assert(b41_xml_config_get(xml, B41_XML_MAX_SIZE + 1, argv[2], &output) == -EINVAL);
    assert(b41_xml_config_get(xml, size, "12345678901234567890", &output) == -EINVAL);
    assert(b41_xml_config_get(xml, size, "missing-feature", &output) == -ENOENT);
    assert(memcmp(&output, &before, sizeof(output)) == 0);
    xml[0] ^= 1;
    assert(b41_xml_config_get(xml, size, argv[2], &output) == -EBADMSG);
    assert(memcmp(&output, &before, sizeof(output)) == 0);
    xml[0] ^= 1;
    assert(b41_xml_config_get(xml, size - 1, argv[2], &output) == -EBADMSG);
    assert(b41_xml_config_get(xml, size, argv[2], &output) == 1);
    memset(xml, 0, (size_t)size); free(xml); /* No retained input. */
    assert(fwrite(output.bytes, 1, sizeof(output.bytes), stdout) == sizeof(output.bytes));
    return 0;
}
