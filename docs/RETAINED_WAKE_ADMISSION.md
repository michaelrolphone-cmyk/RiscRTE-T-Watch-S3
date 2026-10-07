# Retained-wake metadata admission

The shared offline store harness conditionally supplies the canonical Runtime
retained-wake backend when both its public SDK and implementation header exist.
The backing image is a fresh RAM value, never physical RTC memory. Admission does
not initialize, consume, stage or commit it. This matches backend availability in
native Runtime without simulating an app invocation or relaxing policy.

The actual Runtime still requires the explicit app manifest, instance0 grant and
strict installed cohort metadata. Missing/malformed/unsupported cohort, a wrong
API/instance or a missing grant fails closed. Historical Runtime sources without
this API compile the unchanged backend path and reject an unknown capability.
The harness never manufactures a retained payload or claims sleep/wake success.

Run scripts/test_retained_wake_store_admission.py with --runtime and optionally
--legacy-runtime. SANITIZE=1 enables ASan/UBSan. Fixtures are explicitly synthetic
metadata, never a product store or target execution proof. Both normal and
rejected admission must invoke zero native/storage operations and leave the
input bytes unchanged. Existing actual-store/ELF admission remains separate.

No Watch app/provider version or product/release configuration changes. This is
supporting shared validation for the future X4 deep-sleep desk-clock integration.
