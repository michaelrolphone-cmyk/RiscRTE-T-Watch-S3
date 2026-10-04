# 0.4.0 touch-direction configuration variant

The user confirmed that the exact original0.4.0 rollback displays correctly.
This diagnostic/configuration variant uses those original shared source pins
and changes only PORTABLE_TOUCH_ROTATION from180 to0 for Springboard, Battery
and Settings. It adds no newer app code, PMU extension, logical navigation,
partial-frame optimization, runtime change or blur transition.

The complete22-file flashed store is checked against the actual original CI
artifact. Only springboard.elf, battery.elf and settings.elf may differ; the
other19 files (including Clock, all physical driver binaries, manifests, board,
boot configuration and grants) must be byte-identical. Original app versions
remain accurate: these are build-policy variants of the same source versions,
not new application releases. Archive/build integrity records are regenerated
for the new bytes. The distinctly named BIN preserves the original rollback.

Old behavior intentionally remains: the original full-frame cadence and fade,
old icon tap rule, touch-based Back and no crown Back outside Clock. Only touch
direction/location in the three shared apps is addressed here. Physical
confirmation is still required. No merger, release or hardware action occurs.
