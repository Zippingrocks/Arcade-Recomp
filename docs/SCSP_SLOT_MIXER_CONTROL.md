# SCSP per-slot mixer control word

Status (2026-10-12): both mixer words at slot offsets `0x14` and `0x16` are
mapped for all 32 SCSP slots with field-aware knownness. This is a
register-interface milestone, not PCM/FM synthesis or audible output.

The [Sega SCSP User's Manual](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf)
maps slots 0..31 at `0x100000 + slot*0x20`. Each slot's word at `+0x16`
contains all 16 documented bits: DISDL[2:0], DIPAN[4:0], EFSDL[2:0] and
EFPAN[4:0]. Address `+0x17` is the low EFSDL/EFPAN byte. The preceding word at
`+0x14` has seven defined low bits, ISEL[3:0] and IMXL[2:0]; the other nine
bits remain reserved and are not manufactured as zero readback.

`runtime/scsp_slot_mixer.hpp` implements these two words:

- reset contents remain unknown independently for every byte and slot;
- consuming reads require all requested bits to be known;
- byte and aligned word writes establish exactly the written lanes;
- discarded reads are accepted because the manual assigns no read side effect
  to this mixer word, allowing MC68000 CLR's mandatory read-before-write; and
- every other slot offset, the gap after `+0x17`, odd word access and addresses
  outside the 32-slot range fail closed.

This does not implement or infer slot key state, waveform addressing,
envelopes, LFO, pitch, sample fetches, mixing arithmetic, DSP execution,
timing, interrupts or reset values.

## Tests and original-byte result

ROM-free native tests cover all 65,536 word values, both byte lanes, all 32
slots, invalid offsets, knownness, invalidation and strict opt-in. A generated
indexed loop matching the original instruction form clears the low byte of
slots 0..17 and records exactly 18 discarded reads plus 18 writes.

After the complete DSP clear, the authenticated 257-state explorer reaches the
original nested slot initializer. It writes values `0, 8, ... 120` to the
documented ISEL/IMXL byte of slot 0 and then reaches:

```text
PC 0x0060022e: CLR.L ($0c,A0)
denied read: 0x0010000c, width 2
completed instructions: 283336 / 283338 / 283339 by signature route
```

All paths record the earlier 18 final-mixer clears and 16 input-mixer writes.
The next bounded task is the documented slot volume/FM control at `+0x0c` and
`+0x0e`; no slot synthesis or key-on behavior is implied.

No percentage changes: audio and SCSP remain 0%, sound-ROM execution remains
10%, overall HOTD1 remains about 10%, and Gates A/B/C remain open.
