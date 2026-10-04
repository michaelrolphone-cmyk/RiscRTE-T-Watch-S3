# Alarm service target-loader startup correction

The user confirmed `twatch-s3-face-picker-clock-0.6.0-d7b1b641.bin` displays
correctly, while the subsequent Alarm Clock and Wi-Fi builds show static.
The supplied Alarm log identifies Runtime `8688f920` and reports
`alarm-service: elf-open-failed rc=0 (0x0)` after manifest admission. The user
reported the same error from Wi-Fi Settings 1.1.0. The current Runtime 0.1.10
source has the same native loader collision.

The physical provider graph loads each hardware instance with
`esp_dlopen_instance`. These modules all have the deployed basename
`driver.elf`. The added software alarm service previously used ordinary
`dlopen` for `alarm-service/driver.elf`. The target `dlmod` registry records a
module's basename and rejects ordinary duplicate names, even when paths differ
and the existing modules are independent hardware instances. Alarm service
therefore fails before its ELF relocation or startup and before Clock loads.

The Runtime 0.1.13 correction gives every graph-owned provider node its own ELF
mapping. Singleton identity, repeated acquisition and reference counts remain
owned by the provider graph. Ordinary `dlopen` duplicate rejection stays intact.
No panel commands, framebuffer, power rails, SPI/DMA implementation, app feature,
partition or stored file is changed by this correction.

## Why previous integration checks missed it

The real-source Clock tests previously loaded native host modules with the
operating system's `dlopen`. That implementation distinguishes full paths; it
does not implement the target's basename registry. Thus actual policies,
provider source and Clock rendering could pass while the target would stop
before starting Clock. This was a verification gap, and earlier completed
software checks did not establish physical display operation.

The test now compiles the exact Runtime's production `dlfcn.c` and `dlmod.c`.
Only ELF relocation is adapted to execute native host modules; the production
registry performs naming, admission, lookup and removal. The unchanged full
store policies drive production Runtime/CpuPort, selected provider sources and
the actual Clock. The previous Runtime must reproduce the exact Alarm startup
error without loading Clock, and the corrected Runtime must render complete
frames and fully unload. Final image validation repeats this path on bytes
extracted from the assembled BIN. Host peripheral models and target ELF layout
checks still do not qualify physical SPI, memory/cache behavior or display output.

Historical Alarm stores can be tested with their exact `--watch-source`, System
Apps and Utilities pins. `--registry-support` supplies the test adapter while
the production registry itself is compiled from `--runtime`, allowing exact
before/after reproduction without rewriting a manifest or boot policy.

## Paired update lane

The update lane pins Runtime 0.1.15, carrying the same provider mapping repair
and explicit KV v2 prerequisite. Its native registry now gates every paired
profile and the common/raw store, including both software update services.
Five real default Clock outcomes exercise successful confirmation, early health
failure, lost frame health, confirmation refusal and native retention. Native
transport and bank writes remain forbidden during Clock startup. The unchanged
44-file delivered store remains the preservation reference until the separately
owned Nova app integration establishes its exact replacement inputs.
