# Watch File Browser integration

The current cohort adds the NOVA File Browser 1.4.0 and a distinct folder icon.
It receives only the native `storage.installed-files@1` capability at instance0,
plus the existing display, touch, battery, preferences, alarms, RTC, quick-radio
and motion-wake capabilities. It does not receive an unrestricted volume or raw
filesystem import. Its portable manifest is separate from the unchanged legacy
Reader File Browser profile.

Installed browsing is read-only. Runtime exposes admitted app/provider ELF and
manifest paths; private boot/provisioning inputs, NVS and arbitrary files are not
included. The app supports directory navigation, natural ordering, filtering,
the standard Points keyboard, file details and bounded byte previews. Nested
Back stays inside the browser. Root Back returns to Apps, while an already
queued quick-control handoff keeps its destination. Failed native close retains
the app and its visible error instead of discarding open resources.

The existing paired store layout is preserved. To fit the expanded app cohort,
current app packaging removes local symbols and debug metadata that the loader
does not require. Every original full ELF is retained in the current-app artifact's
`debug/` directory. Each app records original/compacted hashes, sizes, the exact
objcopy version and options, and its compaction proof. These sidecars are not
installed into the executable store.

Verification compares allocated content, entrypoints, imports/exports, dynamic
and global/weak symbols, and every retained relocation's target, including
referenced local static symbols. Section alignment, entry stride, order and
links are preserved. Program-header offsets and content are also compared,
normalizing only the ELF header fields that locate the rewritten section table. Unit tests corrupt these fields and require
rejection without changing the original output. The actual Runtime lifecycle
suite also executes original and compacted host ELFs and requires identical
results. Historical custody lanes keep their original ELF bytes. Full target
builds, exact store packing/round-trip and actual-store Runtime checks remain
required before a candidate is called ready. Software checks do not qualify
physical touch, storage media, sleep power or wake reliability.
