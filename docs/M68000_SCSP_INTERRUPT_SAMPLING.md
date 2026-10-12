# MC68000 sampling of SCSP interrupt state

Status (2026-10-12): instruction execution with a lowered MC68000 interrupt
mask continues only when the connected bus proves that no higher-priority
request is accepted; an accepted known request now performs bounded MC68000
autovector exception entry.

The generic MC68000 bus exposes a fail-closed interrupt-level observation:
known level zero means no request, 1..7 means an asserted level, and an unknown
observation blocks execution whenever the SR mask is below 7. A mask of 7 can
continue without querying external state because no maskable level exceeds it.
An asserted level above the current mask enters the corresponding level 1..7
autovector. It is never silently ignored.

## Autovector entry contract

The implementation follows Motorola's MC68000 exception frame and the bus
sequence published in application note AN1012. It requires a known A7 and a
fully known saved SR, updates S/T/the interrupt mask, and reads vector
`24 + level` from the absolute vector table. The externally visible cycles are
ordered exactly as documented: PC low stack write, saved-SR stack write, PC
high stack write, vector high read, vector low read. The resulting six-byte
frame is SR, PC high, PC low at ascending addresses.

Exception entry is one successful scheduler boundary and does not execute the
first handler instruction or increment the completed-instruction count in the
same `step`. Unsupported/unknown state and odd stack frames stop before a bus
transaction. A later refused transaction retains earlier accepted bus effects
while CPU diagnostic state remains at the pre-entry boundary; this is not a
claim to model a secondary physical bus-error frame.

The SCSP interrupt controller derives its sound-CPU level from exact register
knownness. For each factor, an unknown enable blocks the proof; a known-disabled
factor cannot interrupt regardless of pending state; and a known-enabled factor
requires known pending state and, when asserted, a known three-plane level.
The highest asserted level is returned.

At the authentic `MOVE #$2200,SR` boundary, startup has established:

```text
SCIEB value / known mask: 0x00c8 / 0x07ff
SCIPD value / known mask: 0x0000 / 0x00c8
```

Thus every enabled factor (MIDI input and timers A/B) is proven not pending.
Unknown pending bits belong only to disabled factors and cannot be accepted.
This is a state proof, not an assumption that external interrupts never occur.

Native tests cover every mask/level pair, unknown observation, controller
unknownness, highest-level selection, exact exception frame/bus ordering,
partial refusal, vector selection and the authentic SCSP enable/reset state.
The complete ROM-free Linux suite passes 773 tests in 214.148 seconds.

Across all 257 authenticated startup classes, execution advances from
`287064 / 287066 / 287067` to `308029 / 308031 / 308032` instructions. It
performs a second complete DSP register clear and reaches:

```text
PC 0x00600280: MOVE.B D0,(A0)+
denied write: 0x00100700, width 1
```

Later work resolved the COEF upload and bounded jump table; authenticated sound
startup now stops at the identity-gated sample-ROM read at `0x00a9d9f4` until
the legally supplied MPR-19721/MPR-19722 chips are available. Level-7 edge
history, interrupt-acknowledge electrical timing, RTE, continuous timing,
synthesis and audio remain absent. Percentages stay unchanged and Gates A/B/C
remain open.
