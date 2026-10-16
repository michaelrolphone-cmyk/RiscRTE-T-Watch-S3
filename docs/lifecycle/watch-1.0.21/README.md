# Watch HID test increments

The original build recipes and six sealed host qualification receipts are
preserved here. Run `python scripts/check_hid_increment_custody.py` to restore
the bounded Watch-only history, verify its exact commit/tree identities, and
check both complete-image admissions and all 200 scope mutations. Dependency
source remains in its own repository.

The original Watch 20 recipe is `15624cb108c2ba65b35cd6b20283a2edff2bb415`.
Watch 21 is `b44d8ee0159464e9fd2be20c02092c6596573860`. Check out these restored
commits when reproducing the corresponding frozen images: the recipe commit
is part of each cohort's identity. A new source checkout produces new provenance.

Watch 20 adds tap-then-drag and two-contact XY scrolling with axial locking and
diagonal free movement. It selects HID app 0.1.14 and BLE HID 0.1.3. Watch 21 then
changes only BLE HID to 0.1.4, its manifest and cohort identity. All 23 apps and
native Runtime 0.1.73 remain byte-identical to Watch 20. The public provider
checkpoint is Drivers PR20 head 58ad37140bd86bd2247bfa3244c4acc8942b2bd8;
its BLE HID directory exactly matches built local aa0b9cc08b9a3d8a7a8a9410d1507467cbd980f9.

Full initial images are 16 MiB, installed by erasing flash and writing at 0x0.
They erase settings, Bluetooth bonds, saved events and training/model data.
The recipes also preserve paired payloads, but neither these receipts nor this
draft qualifies a preserving transaction, live update feed or hardware result.

Watch 20 SHA256: `bda601dad85ebb8e9c824edcb97827bd818a9eacf684c38c271e1aa27e6d378a`.
Watch 21 SHA256: `4ad9155ca9ec94c440e9d4c6c868947bae0a0d7868f9f416929ca18bbca8404b`.

Each exact image passes actual Runtime whole-store and cohort admission in
normal and ASan/UBSan modes: 95 files, 46 ELFs, 16 policy rows, zero hardware or
storage calls. Each strict scope verifier rejects 100 mutations. LeakSanitizer
is disabled in the traced host environment. Target machine execution remains
a separate hardware test.
