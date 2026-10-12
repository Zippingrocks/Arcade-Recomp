# MC68000 sampling of SCSP interrupt state

Status (2026-10-12): instruction execution with a lowered MC68000 interrupt
mask now continues only when the connected bus proves that no higher-priority
request is accepted. Interrupt exception entry itself remains unimplemented.

The generic MC68000 bus exposes a fail-closed interrupt-level observation:
known level zero means no request, 1..7 means an asserted level, and an unknown
observation blocks execution whenever the SR mask is below 7. A mask of 7 can
continue without querying external state because no maskable level exceeds it.
An asserted level above the current mask also blocks until autovector exception
entry is implemented; it is never silently ignored.

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

Native tests cover every mask/level pair, unknown observation, asserted-level
refusal, controller unknownness, highest-level selection and the authentic
SCSP enable/reset state.
The complete suite passes 762 tests in 208.949 seconds.

Across all 257 authenticated startup classes, execution advances from
`287064 / 287066 / 287067` to `308029 / 308031 / 308032` instructions. It
performs a second complete DSP register clear and reaches:

```text
PC 0x00600280: MOVE.B D0,(A0)+
denied write: 0x00100700, width 1
```

The next blocker is the original program's byte-stream upload into the 13-bit
SCSP COEF file. Correct work must determine the physical handling of upper
reserved/sign-extension bits and byte lanes; relaxing the existing field mask
just to accept the data would be a shortcut. Interrupt exception entry,
continuous timing, synthesis and audio remain absent. Percentages stay
unchanged and Gates A/B/C remain open.
