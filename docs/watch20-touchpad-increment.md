# Watch 1.0.20 isolated touchpad test increment

Build with `scripts/build_touchpad_increment.py` using the pinned roots recorded
in `apps/touchpad-increment-120.json`. Supply the exact delivered Watch 1.0.19
full BIN and its extracted 95-member store, the supporting Runtime 0.1.73 native
candidate, GCC 8.4.0, and a new output directory. Python requires pyelftools and
esptool (the existing provisioning virtual environment supplies both).

The two HID apps use all Watch19 feature flags and its pinned production
System adapter, navigation, sleep, context, and radio inputs. The compiler's
actual dependency closure is checked before and after compiling. Only the
common Utilities HID source/header is replaced. The prequalified BLE provider
is admitted by its fixed binary digest and clean source build receipt.

The exact seven changed store paths are the two app ELFs and manifests,
BLE HID provider ELF and manifest, and cohort.json. Other 21 apps, providers,
board, boot policy, grants, native firmware, partitions and initial app-data
bytes remain identical. The versioned app manifests retain their authority.
The full image keeps demand-retained provider activation.

The recipe validates packed-store round trips, partition placement, full BIN
extraction, actual Runtime whole-store admission and native-ELF cohort admission
in ordinary and AddressSanitizer/UndefinedBehaviorSanitizer builds. LeakSanitizer
is disabled because the executor uses ptrace. Run
`scripts/check_touchpad_increment_scope.py` against the actual old/new stores
for mutation refusal evidence. `--verify-source COMMIT` repeats source, binary,
store and packaging custody checks without compiling or running admission.

The full 16 MiB BIN is an INITIAL installation image that ERASES DATA. It is
not a data-preserving upgrade. A paired payload is built for separate testing,
but this recipe does not qualify a preserving transaction or deploy a feed.
No device operations or physical qualification are performed. Source and proof
are saved locally; nothing is published by these scripts.
