# SCSP slot key execution

Status (2026-10-12): the original sound initializer now completes its full
32-slot setup loop using the documented SCSP `KYONEX`/`KYONB` command. This is
key-state control only, not sample generation, envelopes, timing or audio.

The Sega SCSP User's Manual, section 4.2.1, defines slot word `+0x00` as
`KYONEX`, `KYONB`, source-bit control, sound-source control, loop control,
PCM width and the upper start-address bits. `KYONEX` is write-only. Writing
one to it executes every slot's registered `KYONB` state simultaneously; it
does not require a later zero write, and a command in any slot applies to all
32 slots.

`runtime/scsp_slot_key.hpp` implements that cross-slot behavior directly:

- the 13 documented bits are accepted and the three reserved high bits fail;
- the write-only execution bit is not retained or exposed as readback;
- byte and word writes establish only their documented readable fields;
- every execution copies each known `KYONB` registration into a separately
  tracked active-key state; an unknown registration produces unknown active
  state rather than a guessed reset value; and
- lower-lane reads require all eight readable bits, while upper-lane and word
  reads fail closed because they include write-only `KYONEX`.

The original loop writes high byte `0x10` to `+0x00` once per slot. Each write
therefore proves the current slot's `KYONB=0` before executing all slots. The
first execution knows only slot 0 is off; knowledge grows by one slot on each
iteration; after the 32nd execution, every slot's executed key state is known
off. No power-on contents are assumed.

Native tests exhaust all 65,536 word values and all byte values, verify both
lanes, reserved-bit refusal, write-only reads, partial knownness, arbitrary
cross-slot on/off patterns, unknown propagation, all 32 progressive stop
commands, bus integration and the original `MOVE.B D0,($00,A0)` instruction
shape. The complete suite passes 752 tests in 202.874 seconds.

Across all 257 authenticated startup classes, the original program records
exactly 32 key writes and 32 cross-slot executions, completes the entire slot
loop and reaches:

```text
PC 0x00600256: MOVE.W (A1)+,(A0)
denied write: 0x00100418, width 2
completed instructions: 285113 / 285115 / 285116 by signature route
```

The new address is the manual-defined Timer A word (`TACTL[2:0]`, `TIMA`) in
the SCSP common-control region. Timer register state and clocking are not part
of this unit. PCM/FM synthesis, sample fetch, envelope progression, DSP
execution, interrupt timing and audible output remain absent. Accordingly,
`audio.scsp` stays at 0%, overall HOTD1 stays about 10%, and Gates A/B/C remain
open.
