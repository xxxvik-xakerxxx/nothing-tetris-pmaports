/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_MFG0_H
#define MT6878_GPUEB_MFG0_H
struct platform_device;
struct mt6878_gpueb_mfg0;

/* Synchronous parent transaction, all calls on the acquiring task. Parent
 * must already be bound, runtime-PM enabled and attached to native MFG0.
 * Acquire holds device_lock until finish. Never call from probe, remove,
 * PM callbacks, IRQ context, or while holding a supplier/consumer lock.
 *
 * A negative resume result means PM resume was attempted:
 * the PM reference and module/device pins are quarantined. The mutex is
 * released before returning the failure; no task-owned lock crosses return.
 * Preserve this handle through the boot; no retry or automatic unwind.
 */
/* Split form for claiming SRAM/resources while locked BEFORE PM resume.
 * Prepare has no power side effects; successful finish before resume releases
 * only lifetime pins. Success paths must finish on the same task before return.
 */
int mt6878_gpueb_mfg0_prepare(struct platform_device *parent,
	struct mt6878_gpueb_mfg0 **result);
int mt6878_gpueb_mfg0_resume(struct mt6878_gpueb_mfg0 *scope);
/* Actual downstream failure: retain pins/usage and release the task mutex.
 * Caller retains the failed object. No resource disposal or OFF is inferred.
 */
int mt6878_gpueb_mfg0_quarantine(struct mt6878_gpueb_mfg0 *scope, int error);
/* Call the existing reset-provider register/prepare on the SAME parent/task
 * while this transaction is held; it borrows its own get_if_in_use reference.
 * Finish only ends this synchronous PM transaction. It proves neither OFF
 * nor that firmware, rails, clocks, reset release or DMA are safe.
 */
int mt6878_gpueb_mfg0_finish(struct mt6878_gpueb_mfg0 **slot);
#endif
