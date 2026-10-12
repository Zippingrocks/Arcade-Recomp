# SCSP per-slot passive control words

Status (2026-10-12): the passive words at slot offsets `0x0a..0x16` reached by
the original initializer are mapped for all 32 SCSP slots with field-aware
knownness. This is a register-interface milestone, not PCM/FM synthesis,
KEY_ON execution or audible output.

The [Sega SCSP User's Manual](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf)
maps slots 0..31 at `0x100000 + slot*0x20`. Each slot's word at `+0x16`
contains all 16 documented bits: DISDL[2:0], DIPAN[4:0], EFSDL[2:0] and
EFPAN[4:0]. Address `+0x17` is the low EFSDL/EFPAN byte. The preceding word at
`+0x14` has seven defined low bits, ISEL[3:0] and IMXL[2:0]; the other nine
bits remain reserved and are not manufactured as zero readback.

The same model now covers the fields that the initializer reaches before key
execution:

- `+0x0a`: LS, KRS[3:0], DL[4:0], RR[4:0] (15 defined bits);
- `+0x0c`: SI, SD, TL[7:0] (10 defined bits);
- `+0x0e`: MDL[3:0], MDXSL[5:0], MDYSL[5:0] (all 16 bits); and
- `+0x12`: RE, LFOF, PLFOWS, PLFOS, ALFOWS and ALFOS (all 16 bits).

Reserved bits remain unknown. Writes that set them are rejected, and a
value-bearing read succeeds only when every requested bit is established.
Discarded CLR reads preserve the MC68000 bus transaction without inventing a
reset value.

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

After the complete DSP clear, the authenticated 257-state explorer executes
slot 0's input-mixer writes, clears the volume/modulation and LFO/input words,
and writes the TL and envelope-release bytes. It then reaches:

```text
PC 0x0060023e: MOVE.B D0,($00,A0)
denied write: 0x00100000, width 1, value 0x10
completed instructions: 283340 / 283342 / 283343 by signature route
```

All paths record the earlier 18 final-mixer clears, 17 input-mixer writes,
two volume/modulation discarded reads and three writes, and one LFO discarded
read/write. The next blocker is the active KX write at `+0x00`: correct support
must model its documented KEY_ON execution semantics and must not reduce it to
passive storage.

No percentage changes: audio and SCSP remain 0%, sound-ROM execution remains
10%, overall HOTD1 remains about 10%, and Gates A/B/C remain open.
