# Complete preserving Watch updates

Watch 1.0.2 introduces a complete native+bootfs update transaction. The initial
16 MiB image remains an explicitly destructive transition: it overwrites NVS
preferences and initializes the separate app-data filesystem empty. After that
transition, Firmware Update can install a complete compatible application and
provider cohort, including newly added apps or drivers, without rewriting NVS,
app-data, the bootloader or the partition table. App Store still supports ordinary
compatible updates to already installed applications.

The firmware catalog's `paired-cohort` asset is exactly the native firmware image
followed by the 0x510000-byte SPIFFS boot store. It binds both individual lengths
and SHA256 digests, their combined digest, product/version, actual Runtime
version, exact Watch source revision, and the existing ABI2 layout. The boot
store includes the matching `cohort.json`, generated after the native image is
built. Product versions must increase; the candidate Runtime cannot be older
than the running Runtime. A legacy native-only update leaves the installed
product identity in the cloned store for the next complete-cohort update.

The existing inactive-bank transaction verifies the payloads and validates the
complete staged board, graph, application policies, provider/application ELFs
and persistent namespace ownership before marking the pair ready. No staged
provider or app runs during admission. Existing namespace owners cannot be
silently removed or reassigned. Clock health confirmation and the paired bank
journal govern activation and rollback. NVS and the independent app-data volume
remain outside the write regions. These protections do not implement arbitrary
application data-format migration; future incompatible formats still need an
explicit migration and rollback policy.

The Watch builder and existing release publisher share strict identity and
payload verification. The release preparer also invokes production Runtime
cohort validation against the supplied starting store and checks every selected
ELF against the exact native candidate's public symbol tables. Host admission
does not execute target instructions. The final image CI separately checks
actual target relocation/memory requirements and normal/sanitized Clock
lifecycle execution.

An older ABI2 build with Runtime before 0.1.33, firmware update provider before
0.1.3, or no installed cohort identity cannot bootstrap this complete transaction
through Firmware Update. The owner accepted one final full-image transition for
the current test data. Subsequent preserving updates use the built-in client;
the separate experimental Windows installer is not required.

Software transaction tests model interruption and rollback. Physical OTA,
power-loss behavior and device memory/current measurements remain unqualified.
The partition geometry is unchanged from the previously delivered ABI2 image.
