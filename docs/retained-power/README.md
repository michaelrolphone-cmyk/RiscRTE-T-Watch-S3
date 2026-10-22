# Retained T-Watch 1.1.46 power-controls qualification

This additive qualification does not change the released product, production
recipe, source pins, grants, acceptance baseline or any app/provider/native bytes.
It does not select the separate Settings 1.4.2-dev1 or release a new firmware.

The subject is producer `ab9ff33975680c5bb8d9a2e7ed346d0300732a4e` and its
[public 1.1.46 release](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/tag/test-provisioning-1.1.46).
Exact release CI [39026555734](https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/actions/runs/39026555734)
passed native/store admission for all 61 ELFs, including the byte-retained Settings
1.3.25. It did not execute those Xtensa apps or test hardware.

## Bounded scope

1. Independently download the public store, native evidence, source lock and CI
   provenance; verify pinned lengths and hashes before using them.
2. Decode the actual 125-file store, retain Settings `fa1c87a1…` (142164 bytes),
   Home `f376d722…` (554744 bytes), app namespace-1/power/display/input grants and
   provider bindings. Check every unchanged baseline file.
3. Recompute linked Runtime/workspace placement from the actual released native
   ELF and verify every locked native input. Static memory evidence is not live
   heap availability or a measured application/provider allocation peak.
4. Reconcile the exact retained Settings producer and selected flags, then test
   its actual mode/timer Save/readback and Home consumer paths without replacing
   production logic with a duplicate model. Preserve any unresolved boundary.
5. Add rejection controls for changed artifacts, sources and capability bindings.

This first durable checkpoint covers artifact/structural validation. Behavior
qualification is not yet claimed. Settings source attribution cannot be inferred
from the later System pin used to build Home. The T054 recipe and manifest-only
version increment are being reconciled before running producer-bound tests.

## Installation and physical boundary

The published factory image is a destructive offset-zero installation. It erases
existing saved data. No preserving update kit is established. Native firmware and
store must remain paired; no device or radio action is part of this work.

Physical sleep/wake, display/input restoration, current consumption and live
memory fit remain untested. A host fixture or successful ELF admission does not
close those boundaries.

## Reproduction

Use Python 3 with pyelftools 0.32 and a clean checkout of the exact product
producer. Run `python tests/retained_power/qualify.py --product /path/to/producer
--assets /path/to/cache --output /path/to/report.json`. The cache is rehashed on
every run. The qualification workflow has read-only contents permission, no
publishing job, no hardware tool and no production build step.
