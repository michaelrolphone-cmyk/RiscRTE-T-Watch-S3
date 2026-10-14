# Reproduce T023 preserving components

`profiles/t023-reproduction.json` is the portable recipe: exact public component
pins, complete released baseline file inventory and factory hash, full Home and
Springboard feature flags, expected component hashes, and parameterized build and
composition commands. It uses separate System source pins for the provisioning
provider and the already-qualified RGB client. No whole-tree merge is required.

Use the exact pinned GCC 8.4.0 toolchain and Python with pyelftools. Supply absolute
paths for each placeholder. Clone/check out each public source pin before running
its command. The Runtime SDK's used header hashes are recorded separately from
the final product-native source. Verify them before rebuilding providers; the
original build receipt truthfully records local Runtime 100540a2. Never relabel an
existing artifact as built from another commit.

Verify the downloaded factory asset SHA-256 and every extracted baseline filename
and hash against the recipe before composition. The entire baseline is retained.
The factory asset is an input for reconstruction, not an instruction to flash or
erase a device. All build outputs, original-ELF sidecars and logs belong outside
source checkouts and outside the composed store.

Run the recipe commands in this order:

1. `home`, using the exact Shared/System/Utilities pins and selected preferences.
2. `springboard`, which runs this product's `scripts/build_t023_springboard.py`.
   It imports the pinned RGB compiler recipe, materializes only the pinned bridge
   sources, retains every original feature define, and adds package discovery.
   It preserves the complete baseline manifest and appends only optional
   installed-apps and storage-volume declarations. The same client tolerates a
   missing SD grant on internal-only Watch.
3. `catalog` and `internal`, with `NATIVE_APP_CC` explicitly set to the recipe's
   compiler path. Catalog product identity must exactly equal the baseline cohort.
4. `compose`, only after obtaining the exact native firmware and a verified
   native-selected-provider manifest list. The recorded selection is empty
   because the examined native configs had no policy-header override and their
   selector returned an empty set. Reverify the exact final native inputs; do not
   infer that hardware platform capabilities are selected native driver images.

The Springboard builder requires a new output directory and checks the exact RGB
source commit, compiler binary, baseline manifest, source recipe, ABI imports and
exports, Runtime ELF validation, and expected final ELF bytes. It never changes
source or downloads inputs. Its generated build receipt contains the exact command.

Watch retains its NVS Home/Springboard preferences, internal package volume 0,
and no SD provider or SD grant. Its discovery client handles the absent external
volume through the native internal service. No SD assets are fabricated.

Final feed profiles explicitly use `time.cloudflare.com` for SNTP, as selected
by the user. The recipe makes no implicit time-source or hosting choice.

Before release, publish this recipe checkpoint and use that full public commit as
`cohort.source_revision`. Regenerate the exact migration header from the actual
baseline/candidate snapshots, include corrected native driver digests and all
product-native inputs, rebuild native firmware, and regenerate its cohort binding.
Complete packed-store, graph, native pairing, preserving-update and migration
admission must pass. Current component reproduction is not final native admission,
a release, or hardware qualification.

Tests: `python scripts/test_t023_reproduction.py` and
`python scripts/test_t023_boot_profiles.py`. Set `T023_SPRINGBOARD_REPLAY` and
`T023_HOME_REPLAY` to separately built component directories to check the exact
ELF and generated-manifest hashes recorded in the recipe.
