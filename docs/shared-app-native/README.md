# Published shared-host native integration

This additive recipe qualifies a Watch 1.1.47 candidate from the exact published
1.1.46 release. It integrates Runtime 0.4.18 (combined transfer-mode and capture-safe
resident attention source) and the repeat-qualified automatic-provisioning Home 0.23.1. It does not
change or redistribute the unpublished Spectrum app implementation.

`source-pins.json` fixes all dependency revisions. The workflow checks out the exact
owning commit, uses the pinned ESP-IDF container/compiler, downloads and verifies
the released factory/store/feed assets, repeats the Home build, and runs the new
source-locked native builder. Historical recipes and their guards remain unchanged.

Only `default.elf`, `default.json` (version only), and the necessary native firmware
cohort binding may change in the decoded store. Every other internal file, every
boot policy/grant, and the original package feed must remain byte-identical.
The builder verifies native ELF/BIN identity, actual compiler inputs, partitions,
physical backend selection, target memory bounds, all store ELF admissions in
normal and sanitized modes, current Home lifecycle/provisioning compatibility and
settings selection. It retains source locks, compiler/build evidence and test logs.

Run the owning `Published shared host native integration` workflow for the full
native build. The lightweight package, fetch and builder tests do not substitute
for that build. Output is a software-qualified candidate, not a release, feed,
preserving-update kit, flashed device, or physical acceptance. The explicitly
named factory candidate erases data if flashed; this workflow never flashes it.

The selected released app/provider set remains intact. Full Spectrum delivery is
separate from this Runtime/Home integration unit. No unavailable hardware result
is represented as a pass.

The native profile remains Watch provisioning, not Wave transfer mode. The new
linked layout guard requires the reviewed 2800-byte serial workspace while
retaining 288-byte boot view, 15208-byte package workspace, 32 platform slots,
external placement and the existing allocator/lifecycle checks. The complete
released bootloader and protected factory ranges remain byte-identical; the newly
compiled bootloader is build evidence only. The unchanged old package feed is
retained as baseline evidence, not advertised as a feed for the new candidate.
