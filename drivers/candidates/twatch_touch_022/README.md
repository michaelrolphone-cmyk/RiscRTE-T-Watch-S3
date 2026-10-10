# Opt-in FT6336U touch 0.2.2 candidate

Based on the exact accepted current 0.2.1 source at public Watch main
`db5f6c5ba1a71ed3fcc22ff29847397a050b7ee4`, SHA256
`01b5247d473f3bc7ce34a6de79d259854902637bf78547ce3cbe53a4e407fbc6`.
This directory is an explicit candidate. Accepted `drivers/current/twatch_touch`
0.2.1, historical 0.2.0, release planning, published tags and product recipes
are unchanged. No default selects 0.2.2.

The only provider change is atomic-report emission order: removed UPs, new
DOWNs, then retained MOVEs. Every previous MOVE, including unchanged positions,
remains emitted. Wire order within each phase and cross-report order remain.
This delivers second-contact cancellation before simultaneous motion and
preserves an old contact's release when a different ID replaces it in one
report. No timing heuristic, second event queue or allocation is added.
Configuration, clamping, subscriptions, gap behavior, ownership and complete
hardware/teardown behavior are unchanged. The FT6336U sleep register remains
unwritten.

Run `scripts/test_touch_contact_order.py --system PATH --output NEW_DIRECTORY`
for the actual candidate, original Watch transport/resource mocks and unchanged
shared reducer. It includes original driver contracts and ten ordered-input
cases on nominal and alternate wiring, normally and with ASan/UBSan.
`--baseline` records the preserved 0.2.1 failures separately.

Higher-level Watch keyboard, gesture and secure HID qualification is being
sealed separately. These are software/provider tests, not physical hardware
qualification or a rebuilt/selected Watch product. See `reservation.json` for
live branch/tag version custody. Target compilation uses the existing current
provider flags and explicit source selection; no accepted build is replaced.
