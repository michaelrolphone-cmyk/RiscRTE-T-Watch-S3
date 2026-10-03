# Source provenance and notices

- Canonical SDK headers are copied from
  [T5S3-Reader 3d9bc4f](https://github.com/michaelrolphone-cmyk/T5S3-Reader/tree/3d9bc4f373679f5ae8dd184db6a8d0afa5a40231/sdk/driver).
  Its MIT notice is retained in Reader-MIT.txt. Exact hashes: sdk/SOURCES.json.
- Shared GPIO/SPI/radio and hardware mapping headers, Wi-Fi source/API, and common
  display/transport helpers originate in the same owner's
  [Garden PR69](https://github.com/michaelrolphone-cmyk/Garden-Controller/pull/69).
  Raw platform headers are pinned to1f7fb82efec08cf8751057d84e707f20be2fb7a5;
  the hardware mapping header/contract/common schema follow
  7e30afc407c86f34364cbfa2035d6f7893fdea8c with the same C layout. Common helpers
  were adapted from783a88daeb0af853d77acfed52ef66b96d9d156e. No separate license
  was found in that repository snapshot; no new third-party license grant is
  asserted. Reuse follows the repository owner's explicit task instruction.
- LILYGO hardware facts/init sequence were checked against LilyGoLib92f2ac3f.
  LilyGoLib-MIT.txt preserves its upstream notice. No vendor binary/firmware is
  redistributed by these packages.
- LoRa commands were cross-checked against RadioLib
  [b0dd65d489b4c2b4e2fb2ff029d55ae0c3d649c8](https://github.com/jgromes/RadioLib/tree/b0dd65d489b4c2b4e2fb2ff029d55ae0c3d649c8/src/modules),
  especially SX1280 SF correction and SX1262 IQ/PA workaround registers. The
  packet engine here is a new C implementation, not a vendored RadioLib library.
- PMIC register meanings were cross-checked against XPowersLib
  [d6997586e68f65afd51baa775903df930db39821](https://github.com/lewisxhe/XPowersLib/blob/d6997586e68f65afd51baa775903df930db39821/src/XPowersAXP2101.hpp).
- RTC and haptic registers were checked against the primary
  [NXP PCF8563 datasheet](https://www.nxp.com/docs/en/data-sheet/PCF8563.pdf) and
  [TI DRV2605 datasheet](https://www.ti.com/lit/ds/symlink/drv2605.pdf).
  Those documents are linked, not reproduced. Semtech product page fetches were
  blocked with403; no claim is made that a new Semtech datasheet was retrieved.
