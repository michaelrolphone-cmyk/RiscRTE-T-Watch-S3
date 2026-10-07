# Historical panel package custody

The current power-lifecycle repair uses panel 0.4.2. Historical Clock, Alarm,
Points, Wi-Fi and Update deployment lanes still require the previously reviewed
panel 0.4.1 package. Their version, package-hash and preserved-store validators
remain unchanged.

`custody/panel-0.4.1` contains the complete 26-file target source/header/linker
closure from Watch commit `273b58d64ccc9a7dd66f0659271a942f244edcdf`, plus a
hash-pinned provenance record. It is separate from the older
`custody/sleep-prefix` snapshot, which is not modified.

`build_twatch_drivers.py` continues to build panel 0.4.2 from live sources into
the main catalog. Its existing legacy build step also compiles panel 0.4.1 from
the separate frozen closure into the legacy catalog. `build_clock_deployment.py`
uses the frozen GPIO/PMU/panel catalog and manifests for historical deployments.
The current-app/power-profile paths continue to select the live driver package.

With the pinned Xtensa GCC 8.4.0 esp-2021r2-patch5 toolchain, the frozen output is:

- Package: `driver-twatch-panel-0.4.1-xtensa-esp32s3.rte.zip`, 15,344 bytes
- Package SHA-256: `6b59a6c443becc77ca8240cbc7624bca0865e408e45f46973cf0639f8fd6b90d`
- ELF: 12,604 bytes
- ELF SHA-256: `a7cddc560dc83e9a7ea8f408ed17637098bdc64fb9b02b028749f49c9d782aad`
- Canonical deployed manifest SHA-256: `8d7ab89dd35c8e8dfc3766e11e0ab51ee0c053fbc4b904617eef86e3ccc5be61`

These are the existing immutable baseline values, not newly accepted hashes.
The legacy builder rejects a different package hash, and provenance validation
rejects changed source bytes or a silently rehashed record.

Verification:

```
python scripts/build_twatch_drivers.py
python scripts/check_twatch_drivers.py
python -m unittest discover -s tests -p test_legacy_panel_custody.py -v
python -m unittest discover -s tests -p test_clock_common.py -v
python -m unittest discover -s tests -p test_pmu_sleep_custody.py -v
```

The target custody test compares both catalog generations, the old package and
ELF hashes, and the exact immutable Update baseline manifest/ELF entries. The
Clock/common regression confirms all eight historical profiles select panel
0.4.1 despite panel 0.4.2 being present in the main catalog. Existing historical
validators continue to check their full deployments independently.
