# SCSP DSP COEF, MADRS and MPRO register files

Status (2026-10-12): the three manual-defined DSP register files are mapped and
synthetic-native tested. The intervening setting-prohibited span has only the
exact original clear-transaction contract described below. DSP execution
remains unimplemented.

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

The manual's DSP table ends MADRS at `0x1007bf`, labels the intervening
`0x1007c0..0x1007ff` span **Setting prohibited**, and starts MPRO at
`0x100800`. The original production program nevertheless performs exactly 32
discarded word reads followed by 32 zero-word writes there as part of its
320-longword CLR loop. `DspProhibitedClearWindow` accepts only that observed
transaction shape. It exposes no read value, no storage, no byte access and no
nonzero write. In particular, it does not adopt MAME's second-MADRS-decode
interpretation without an independent hardware measurement.

## Tests and original-byte result

ROM-free native tests cover every 16-bit COEF input (including all rejected
reserved-bit patterns), every valid MADRS word, both byte lanes, all 64/32
indices, exact bounds, unknown reads, invalidation and longword CLR ordering.

Across all 257 proven startup states, authenticated original execution records
64 COEF discarded word reads plus writes and 32 MADRS discarded word reads plus
writes. Every state reaches:

```text
PC 0x0060022e: CLR.L ($0c,A0)
denied read: 0x0010000c, width 2
completed instructions: 283336 / 283338 / 283339 by signature route
```

All 257 classes now exercise MPRO continuously: each records 32 prohibited
discarded reads and zero writes plus 512 MPRO discarded reads and writes. No
class diverges before the follow-on slot input-mixer initializer described in
[SCSP_SLOT_MIXER_CONTROL.md](SCSP_SLOT_MIXER_CONTROL.md). No
percentages change. SCSP/audio remain 0%, sound-ROM execution remains 10%,
overall HOTD1 remains about 10%, and Gates A/B/C remain open. The remaining
uncertainty is the prohibited span's general hardware behavior; the bounded
contract establishes only what this original instruction sequence requires.
