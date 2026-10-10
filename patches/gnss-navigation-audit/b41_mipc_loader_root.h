/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MIPC_LOADER_ROOT_H
#define B41_MIPC_LOADER_ROOT_H
#define B41_MIPC_PROVIDER_COUNT 10u
#define B41_MIPC_XML_SIZE 5087u
#define B41_MIPC_XML_TARGET "vendor/etc/MNL_Config.xml"
/* Dedicated, externally supervised child only; root is a fresh root-owned
 * empty absolute directory. Descriptors come from LoaderResources.move in its
 * fixed order and remain parent-owned until terminal reap. This validates seals
 * and layout, NOT caller-supplied ELF authentication or runtime service grants.
 * Copies sealed bytes into a bounded private tmpfs and remounts it read-only;
 * never executes loader, dlopens, chroots or installs weaker device policy.
 * On ANY error child must exit: partial mounts are namespace-owned, not reset
 * or retried. The established isolation launcher must be explicitly reviewed
 * to consume this prepared root before it can be an executable runtime path.
 */
int b41_mipc_loader_root(const char *root, const int *providers, unsigned count);
/* Same fixed providers plus genuine independently pinned load-only /probe and
 * B4.1 libMNL descriptors. No INIT-capable helper or arbitrary executable slot. */
int b41_mipc_loader_root_probe(const char *root, const int *providers,
    unsigned count, int probe, int mnl);
/* Separate 13-FD configuration snapshot, NOT admitted by the 12-FD launcher.
 * Same providers/probe/libMNL plus the fixed B4.1 XML from ProbeXmlResources.
 * Caller supplies a fully sealed independently pinned XML lease, mode0444.
 * Adds only /vendor/etc/MNL_Config.xml; /data stays absent in this fresh root.
 * Shape/seal checks are not authentication. All FDs stay caller/supervisor-owned
 * through terminal reap; partial failure requires child exit, never retry.
 * Does not invoke the OEM reader, preinitialize globals or authorize INIT.
 */
int b41_mipc_loader_root_probe_xml(const char *root, const int *providers,
    unsigned count, int probe, int mnl, int xml);
#endif
