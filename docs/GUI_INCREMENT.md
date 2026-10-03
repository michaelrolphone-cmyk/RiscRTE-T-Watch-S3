# Watch GUI correction 0.4.5

Built from physically improved0.4.4. Physical driver ELFs/manifests, seven mapped instances, board wiring and runtime remain byte-identical to the confirmed baseline.

Normal navigation uses `clock.elf`, built from the same Clock source with an explicit entry policy. It performs a60ms retained outgoing→Clock blur fade with no blank or boot intro. `default.elf` is the boot entry. Actual successful light-sleep wake runs the intro in either build; no uptime heuristic, firmware UI state, launch-context ABI or PMU UI state is used. Springboard Back and Clock icon select normal Clock; Settings/Battery root Back returns to Springboard. Nested Settings Back/cancel remains internal.

Clock samples touch during full-frame drain every8ms and latches the first qualified swipe. An accepted frame finishes before immediate handoff. The shared handoff counts initial drawing time in its60ms phase, with incoming content in the first transfer rather than retransmitting the already-visible outgoing frame. Local identical models improved continuous swipe handoff125/150/190ms→100/100/95ms at25/50/95ms presentation costs; formerly missed fast held swipes now hand off within the current frame. These timings exclude physical ELF loading and are not target benchmarks.

Before light sleep, Clock dims and completes one black frame so an early restoration pulse cannot show the old Clock GRAM. It is not a scrub animation. Refused sleep completes a fresh Clock while dimmed before lighting again. Tests simulate a resume light pulse and check actual retained pixels are black. This addresses retained sleep/wake content, while a cold-reset flash before panel ownership is separately unresolved: PMU rails are enabled before panel backlight claim and before any application loads. More application blank calls cannot close that earlier interval.

The store has24files:13 original board/physical-provider files unchanged, five app ELFs/manifests and app grant policy. The extra Clock build has the same source and capability boundary. No new provider, rail timing, partial transfer, deep/ultra sleep, or additional user app is included.

BIN0x0 overwrites lower8MiB including settings; upper8MiB untouched. Preserve0.4.4 and earlier confirmed images. Software verification does not replace physical feedback. No flashing, merging or release is performed.
