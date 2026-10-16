# Files shared plaintext input: qualified component handoff

Status: held for final integration; not flashed, not delivered, and not hardware-qualified. Do not deliver before 2026-10-12 23:30 UTC.

Files 1.5.34 routes Rename, New Folder, and Find by name through ui.text-input. The ordinary browser, mounted volumes, all file actions, native-time controls and non-SD Open paths remain intact. Plaintext entry retains the existing 127-byte filename and 63-byte filter limits. A backward-compatible optional bounded suffix leaves existing shared-keyboard clients and masked-password layouts unchanged.

Source checkpoint: https://github.com/michaelrolphone-cmyk/RiscRTE-System-Apps/commit/e3fd26c2257cef91c8f6a7b98065b52f1db7a54d
Production source tree: 05ca25fa292f9420a32743b1468f7efee6d2fc78

Components:
- watch-files: exact inherited Watch Files profile, source Open/Nearby preserved, LTO and accepted metadata-only ELF compaction
- watch-hosts: scene 0.4.4 with the inherited compact Watch profile; text-input 0.1.5
- x4-files: exact .101 Files feature profile plus the shared-input selector; one additive grant (17 policy rows)
- x4-hosts: full scene 0.4.4, including Reader and telemetry APIs; text-input 0.1.5

Each directory contains the target files and source-bound build records. No firmware or native Runtime rebuild is required for this delta.

Combined recipe witnesses:
- Watch: https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/commit/d3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453
- X4: https://github.com/michaelrolphone-cmyk/RiskRTE-XTEINK-X4-PRO/commit/6bf5abdf8508f20c1394cc2552a28f1990b73cff

The Watch witness composes over the complete Files/Viewer/Scanner/RTC/Points cohort ec667cd3: 55 admitted ELFs, all 113 store files retained, four free SPIFFS blocks (baseline had two). The X4 witness composes over the .102 RF/RTC cohort 918f3aa7: 43 internal and 48 selected SD ELFs, 128 free blocks, all previous SD files preserved, and two new immutable host images with matching internal fallback bytes. Its cumulative SD overlay contains 14 files. Both full-initial images preserve the exact native firmware and unrelated flash ranges.

These are component-admission witnesses, not the later SD-settings/availability final product union. Integrate the Files source and component selectors into that union and requalify the complete final cohort before delivery. Do not replace newer work with these earlier baseline compositions.

Qualification includes normal and ASan/UBSan Files controller workflows, explicit full-file actions after shared-keyboard return, delayed close and Home/Back cleanup, mount expiry, rapid repeated characters while rendering is pending, exact Watch/X4 Runtime lifecycle matrices, non-SD Open regressions, 42 byte-identical non-editor screens, and existing Points/Scanner clients against the new hosts. See receipts/qualification.json and handoff.json for exact artifacts and log hashes.

Host tests do not execute Xtensa target instructions or qualify physical touch, crown, display, radios, SD hardware, or device resume. Full-initial firmware erases user data if flashed. No flashing was performed.
