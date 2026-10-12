# SCSP per-slot mixer control word

Status (2026-10-12): the final mixer word at slot offset `0x16` is mapped for
all 32 SCSP slots with byte-granular knownness. This is a register-interface
milestone, not PCM/FM synthesis or audible output.

The [Sega SCSP User's Manual](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf)
maps slots 0..31 at `0x100000 + slot*0x20`. Each slot's word at `+0x16`
contains all 16 documented bits: DISDL[2:0], DIPAN[4:0], EFSDL[2:0] and
EFPAN[4:0]. Address `+0x17` is the low EFSDL/EFPAN byte.

`runtime/scsp_slot_mixer.hpp` implements only this word:

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

The authenticated 257-state startup explorer accepts the original program's
18 slot clears. Every state advances from the prior `0x100017` boundary to:

```text
PC 0x006021be: CLR.L (A3)+
denied read: 0x00100700, width 2
completed instructions: 262398 / 262400 / 262401 by signature route
```

All paths record 18 slot-mixer discarded reads and 18 writes. The manual maps
`0x100700..0x10077f` to 64 DSP coefficient words (COEF[12:0]). The follow-up
[DSP register model](SCSP_DSP_REGISTER_RAM.md) now clears all COEF and MADRS
words and stops strictly at the manual's unassigned `0x1007c0` gap.

No percentage changes: audio and SCSP remain 0%, sound-ROM execution remains
10%, overall HOTD1 remains about 10%, and Gates A/B/C remain open.
