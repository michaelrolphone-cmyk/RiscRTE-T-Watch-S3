# Complete Watch test build: HID Accept and SDR capture

Delivered full initial BIN:
`twatch-s3-1.0.7-HID-SDR-FIX-FULL-INITIAL-ERASES-DATA-bma423.bin`

SHA256: `bf6ee05f5d79e3f6f06791d252c8f1ea57695554beaafd6cc68567dd0470d2e4`

**16 MiB at offset 0x0. Erases both banks, NVS/settings, saved Wi-Fi credentials,
alarms/Points and app-data.** This is an original/non-Plus T-Watch-S3 BMA423 test
image, not a preserving OTA. All 22 apps and the prior completed features remain.

## Corrected paths

- Current touch 0.2.1 reports the last emitted sequence in snapshots. The old
  Watch provider reported the next event number, so the HID app treated each
  real contact as a gap and discarded Accept before Bluetooth confirmation.
  The old provider reproduces the failure in the real HID app/System adapter
  fixture. The corrected provider passes both apps, safe cancellation/recovery,
  and normal/sanitized runs. Historical touch 0.2.0 remains unchanged.
- SDR 0.1.3 enables the required dump-engine MAC clock bit after native PHY
  calibration and restores its previous value after capture. Calibration is
  not reset. The clock-aware production fixture reproduces DUMP FAIL without
  that bit and passes with it, including timeout, restore and retained cleanup.
  This requirement is documented in the pinned upstream
  [eSpDR receiver implementation](https://github.com/h0m3us3r/eSpDR/blob/f279bf823eee41796dfd1ac21f13e1ed9b418c82/esp32s3/src/radio.c#L78-L112).
- HID apps 0.1.2 and Waterfall 0.1.5 emit bounded `HID` and `SDR` diagnostics
  through the existing Runtime logger. Pairing numbers and secrets are excluded.
  SDR reports result/stage, dump clock/index/timing, and cleanup state using an
  optional copied diagnostic extension; the original IQ API prefix is unchanged.

## Capturing diagnostics

Open the device's native USB serial connection at 115200. Live messages identify
pairing contacts, accepted/rejected response requests/results, pairing state
changes, SDR capture stages and cleanup. Send `diag` followed by Enter to replay
recent retained diagnostics. The existing journal holds eight recent messages;
later messages can evict older entries and the replay reports losses.

The actual Runtime logger and USB shim were tested with connected, absent and
full USB transport and replay after app return. This is host evidence, not
physical Watch USB/Bluetooth/RF qualification. CI was not awaited for delivery.

`provenance.json` records all pinned sources, component offsets/hashes, app
artifact identities and exact assembly command hash. The original local build
commit 8a6741207ab90cfa1634a812ef472414c8257495 is preserved in the Git bundle,
which requires ancestor 7e1fe325. Published source 47bceb2 has the identical tree
07506acc77502175a68f3fe2160ec87d99e40fa5; only commit metadata differs.
