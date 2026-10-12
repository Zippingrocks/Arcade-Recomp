# SCSP DSP COEF, MADRS and MPRO register files

Status (2026-10-12): the three manual-defined DSP register files are mapped and
synthetic-native tested. DSP execution and the reserved address gap remain
unimplemented.

The [Sega SCSP User's Manual](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf)
defines:

- 64 R/W `COEF[12:0]` words at `0x100700..0x10077f`; and
- 32 R/W `MADRS[16:1]` words at `0x100780..0x1007bf`; and
- 128 R/W 64-bit `MPRO` instructions, exposed as 512 words at
  `0x100800..0x100bff`.

`runtime/scsp_dsp_coefficients.hpp` models independent value knownness for
every word. COEF rejects nonzero reserved bits 15:13 and records only the
documented 13-bit field as known. MADRS uses all 16 register bits; sound-memory
address bit zero is implicitly absent from the named field. MPRO keeps all
four big-endian words of each 64-bit instruction independently observable;
it does not claim to decode or execute that instruction. Normal reads
require every requested bit to be known. Side-effect-free discarded reads
permit MC68000 CLR's mandatory read-before-write without manufacturing an
initial value.

The model explicitly stops before `0x1007c0`. The manual's DSP map ends MADRS
at `0x1007bf` and starts MPRO at `0x100800`; it does not assign the intervening
64-byte gap to either file. The original program does attempt to clear through
that gap, but software intent alone cannot define undocumented hardware
readback or storage.

## Tests and original-byte result

ROM-free native tests cover every 16-bit COEF input (including all rejected
reserved-bit patterns), every valid MADRS word, both byte lanes, all 64/32
indices, exact bounds, unknown reads, invalidation and longword CLR ordering.

Across all 257 proven startup states, authenticated original execution records
64 COEF discarded word reads plus writes and 32 MADRS discarded word reads plus
writes. Every state reaches:

```text
PC 0x006021be: CLR.L (A3)+
denied read: 0x001007c0, width 2
completed instructions: 262458 / 262460 / 262461 by signature route
```

No percentages change. SCSP/audio remain 0%, sound-ROM execution remains 10%,
overall HOTD1 remains about 10%, and Gates A/B/C remain open. The next honest
blocker is independent evidence for the `0x1007c0..0x1007ff` gap; it must not
be silently folded into COEF, MADRS or MPRO. Because authentic execution stops
at the first access in that gap, it does not yet exercise MPRO continuously.
The MPRO proof is therefore synthetic-native: every one of its 512 bus words,
both byte lanes, unknown-read behavior, exact endpoints and the original
256-longword clear-loop shape are tested under GCC and Clang with UBSan.
