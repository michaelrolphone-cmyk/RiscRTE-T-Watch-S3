# T-Watch provisioning integration

The next product recipe starts from cumulative main
`649b897ae928b388c2d1e125f88f7390e827bf79` and the exact delivered
`test-shared-default-1.1.43` factory. All historical recipes and release assets
remain unchanged. Candidate identity is 1.1.44; release and catalog rollout follow
the existing X4, Waveshare, then T-Watch sequence.

The delivered factory was downloaded independently and matched 16,777,216 bytes,
SHA256 `f6b600197087ae93c93752507b89d6be0c248abb528c010da2d280f7a0166f36`.
Its 121-file store contains 59 ELFs and no installation policy. In particular,
Settings remains 142164 bytes,
`fa1c87a1e971d1d64a5d65d8e655d898bbd227a42364f639517ff53ea2966e3e`.
That retained binary is not attributed to a newer System build.

Shared Watch commit `bc72f4dd6ed492943881f4dfab1d04db9ec41aa8`, with its locked
System and Utilities inputs, builds Home0.19.0 using `--automatic-provision`.
Two independent GCC15 target builds produced identical 625648-byte Home ELFs,
SHA256 `db23f172746ab32c0ba9c94d4c7a93d99be5f16247b6f267b48af8d7ca252d6f`.
The common artifact is reused for both watch products. This is target application
link/structural validation, not full native firmware or hardware qualification.

Missing composition consists of explicit native request/package-volume selection,
installed-apps and internal package providers, narrowly scoped Home authority,
and complete bounded product feeds. The implementation must retain every other
application/provider payload and all existing physical-board selections.
T-Watch remains internal-only; no removable volume or serial namespace is inferred.
Fresh-factory self-admission and preserving-transition admission are separate
results. Any namespace-ownership guard remains intact.

Source Atlas immutable source-set version
`c93e1669-26d1-47d8-bb64-89a4833a351c` pins the initial reconciliation sources.
At first trace, exact current pins had incomplete text coverage and no selected
compiler index. Empty trace results therefore establish no absence. Direct exact
Git source inspection supplies the implementation evidence while indexing proceeds.

Native firmware runs only in exact-source GitHub CI. First-start provisioning,
physical profile acceptance, power interruption and real-flash SDK6 NVS faults
remain separate hardware checks.
