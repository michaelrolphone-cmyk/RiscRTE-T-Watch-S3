# Accepted complete Watch 1.0.12

This separate publication lane promotes the exact delivered image which the
owner reported stable and reliable. It retains Runtime 0.1.55, all 22 apps,
22 providers, and every embedded manifest, board, boot, grant and source byte.

The accepted 16 MiB full image has SHA-256
`af958e480a3183bde3f448e97930d56b9aeea567a664428892b917a878d014ff`.
The public catalog filename `twatch-s3-launcher-1.0.12.bin` is a byte-exact
alias of `twatch-s3-1.0.12-FULL-INITIAL-ERASES-DATA-bma423.bin`.
It is an INITIAL image flashed at 0x0, erasing NVS, settings, Wi-Fi credentials,
Bluetooth bonds, alarms, Points, app-data and both banks.

The paired payload with SHA-256
`9fdfaed08238524baec6524fe8915e03f9f5b0c8011f9c5b0027dc530629c2f4`
is not published by this lane. No OTA field is added to the firmware record.
The historical paired proof remains evidence, not a catalog admission claim.

Staging extracts component bytes from the fixed image and independently checks
them against the original build proof and app evidence. Previously published
provider ZIPs/source records remain immutable; new packages retain exact deployed
ELF and source-manifest bytes. The complete `accepted-store.zip` preserves exact
manifest bytes even when an older package used a different JSON serialization.
All 22 app releases carry the deployed ELF and manifest, original licenses,
minimum Runtime/cohort documentation and source provenance. Historical clients
do not enforce these minimum fields; install the complete cohort first. The exact
installed 1.0.7 updater source refuses every proposed 1.0.12 app because its
capability/API authority differs. The ordinary and ASan/UBSan host test covers all
22 real manifests and records, observes zero bank transactions and payload
downloads, and checks a same-authority positive control. This is a production
service admission proof, not a new physical-device or loader-execution claim.

Every new release uses the existing draft-upload/download-verification publisher.
The exact predecessor index commit is `4d6237bd5b06fe88ee41e8e754f37ef1b7aea709`.
The index changes last through a non-force compare-and-swap. Repeating the exact
completed plan is read-only and still verifies every release; other predecessors,
source changes, extra assets and immutable-version collisions are rejected.
The frozen 1.0.7 lane and its custody are unchanged.

`owner-acceptance.json` records the subsequent acceptance without editing older
proofs that still say hardware verification was pending. See `REPRODUCING.md`
for public prerequisites, five original Git bundles and a clean build procedure.
The historical reconstruction-input ZIP is stored in Git as two gzip transport
parts. Staging and hydration restore its exact original bytes with bounded reads
and decompression; the published ZIP, source pins and accepted proof are unchanged.
No release operation accesses a physical device.
