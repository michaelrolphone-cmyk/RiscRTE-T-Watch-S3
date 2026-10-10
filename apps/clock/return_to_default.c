/* clock.elf remains the installed return target. The configured default.elf
 * owns the clock implementation and assets. Runtime's child-return contract
 * starts a fresh default invocation after this module has been unmapped.
 * Keeping this entry point avoids duplicating almost 850 KiB in bootfs.
 */
__attribute__((visibility("default"))) void app_main(void) {}
