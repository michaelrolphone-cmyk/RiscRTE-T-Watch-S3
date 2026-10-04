# Incomplete Frequency Generator checkpoint, 2026-10-04 UTC

## Status and priority

This is a source-preservation checkpoint, **not ready for integration testing,
merge, firmware delivery or physical qualification**. Audio integration is paused
at the user's reprioritization; OTA/App Store work is first. No spectrum Watch
branch, microphone edit or additional audio feature has been started here.

At approximately13:32UTC the execution filesystem was replaced unexpectedly.
The original uncommitted Watch source and every local build/log/evidence file
became unavailable. The exact stable Watch baseline was restored from GitHub and
this independent integration was reconstructed from retained tool-call text.
Do not treat old test results as current or their missing artifacts as evidence.

## Restored source pairing

- Watch baseline: `216e2d73b72cca6c3bcf75ad9ef56466b8861144`,
  branch `fix/watch-runtime-admission`; work branch `feat/watch-frequency-generator`.
- Audio System Apps: `95783cb7071e025b90977dbc331b5d06cfe996f9`, PR32.
- Generator Utilities: `268fe4a86a823185578e5c7d56be7e3d3066052d`, PR14.
- Runtime0.1.12: `e9e409d4b24d43b863956b1185cc2e2e063c0066`, PR10.
- Original Springboard adapter: System Apps
  `83167b245149b1114a0497ab09bf2b410cd715ff`.
- Spectrum owning-source PR15 exists separately at
  `ded2a4c11e4d575bd49de38dc238b29d5ed850af`; it is not integrated by this branch.

All source-owning prerequisites above were already published before the
filesystem replacement. Local re-materialization does not establish artifact
custody or hardware qualification.

## Recovered versus lost

Recovered: additive archive/store/build/final-assembly scripts, opt-in full-store
production-source audio harness, negative custody tests, six-job CI wiring,
source/Runtime requirement pins and integration documentation. Original apps,
board manifests, providers and OTA/App Store code are untouched.

Lost: all target ELFs, nine overlay ZIPs, SPIFFS images, admission reports,
provisional host and sanitizer outputs, compiler/mkspiffs installations and
independent review scratch evidence. No new BIN was produced or delivered.

Before replacement, provisional source runs had observed13 normal cases pass,
target loader success,46-file SPIFFS roundtrip and10 actual-store admissions.
Those observations concern the former uncommitted tree and unavailable inputs;
they are historical debugging context only and **do not verify this checkpoint**.
The complete sanitizer matrix was not finished. Do not copy those observations
into CI receipts, delivery records or readiness claims.

## Required unresolved gates

1. **Target source custody.** Independent review identified that a structurally
   valid new ELF and refreshed `audio-build.json` hashes could pass overlay-only
   verification. Reconstruction adds `verify_target_bytes`: a fresh target
   rebuild from exact clean sources, compared byte-for-byte with Springboard and
   audio ELFs/manifests/catalog/build record. It runs in the target CLI and final
   image builder. A matching rehashed-ELF negative was added. None of these new
   rebuild gates has been executed after reconstruction; review and run them.
2. **Persistent health failure.** The added14th production scenario times out
   after audio has safely closed and Runtime has returned to default Clock.
   Last observed diagnostic: `current=default.elf opens=1 closes=1 writes=4 live=0`.
   Root cause is unresolved. Do not drop/weaken this case or call it a pass.
   Determine whether Clock/service recovery or harness termination is responsible.
3. **Artifacts/tools.** Re-materialize authorized artifacts using a supported
   route and verify their full hashes. One connector URL download returned403;
   that route was stopped. No artifact bytes were recovered by that request.
   Old Watch artifact11302360168/run37198047296:
   `dc5c68405539337066832a6d08ebebd4edeed33524b220861242a9e558b22ece`.
   New Runtime16MiB artifact11304234568/run37205679525,6073704bytes:
   `ee43408d79f9c3c46f3c6010e66baf680a47b1aea4eb5bbc390981c0f111df07`.
   Metadata alone is not proof. The exact component descriptor
   `apps/audio-runtime-artifact.json` is intentionally absent; assembly fails
   without it. Restore official GCC8.4 esp2021r2patch5 and pinned mkspiffs2.230.0.
4. **Re-run all gates.** Rebuild against the final committed Watch head; run
   custody negatives with zero prerequisite skips, every production admission,
   actual app/Clock cases in normal and ASan/UBSan modes, target relocation,
   independent source/target comparison and all existing baseline regressions.
   Establish six successful exact-head CI jobs before assembling any development
   BIN. Re-extract and execute the final BIN store before delivery.

Only Python syntax compilation, JSON parsing and diff-whitespace checks are
permitted for this checkpoint's reconstruction coherence check. No new target,
host, sanitizer or artifact verification result is claimed here.
