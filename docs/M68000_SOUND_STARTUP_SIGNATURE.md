# Original sound startup signature: exhaustive state proof

Status (2026-10-12): the authenticated original program's `ErrorSet` decision
has an exhaustive software-state proof. This is not evidence of physical
power-on RAM values or sound-board reset wiring.

At PC `0x600172`, the program clears D4, compares the longwords at sound RAM
`0x0c08` and `0x0c0c` against `0x4572726f` and `0x72536574` (`ErrorSet`), and
loads byte `0x0c04` into D4 only on an exact match. Both BNE routes and the
exact-match route reach `0x600190`, where `MOVE.W #3,D6` overwrites the
comparison N/Z/V/C flags. X is preserved on every route.

`arcaderecomp/sound_startup_signature.py` authenticates the instruction
semantics with the independent MC68000 decoder and partitions all nine relevant
unknown bytes:

- `(2^32 - 1) * 2^40` assignments mismatch the first longword;
- `(2^32 - 1) * 2^8` match the first and mismatch the second; and
- 256 contain the exact marker and preserve each possible byte at `0x0c04`.

The counts sum exactly to `2^72`. At `0x600194` there are 257 architectural
classes: one has D4=0, while 256 have D4 equal to a fully known zero-extended
error byte. Returning a convenient zero for unknown RAM would select only one
class and remains forbidden.

Public ROM-free native tests execute both mismatch routes, signed/unsigned
comparison boundaries and all 256 preserved bytes through generated C++ with
UBSan. Every instruction semantic in the bounded sequence is guarded against
mutation. The analyzer does not emit ROM bytes or disassembly.

## Authenticated private exploration

`tools/experimental/hotdo_sound_signature_explorer.py` supplies each proven
class as an explicit research premise and runs the authenticated original chip
through the existing strict bus. It is an exhaustive software-state
experiment, not a claim that any particular premise occurred on a cabinet.

All 257 classes clear exactly 458,752 (`0x70000`) sound-RAM bytes and reach the
same next hardware boundary:

```text
PC 0x00600344: CLR.B (0x17,A5,D4.W)
denied read: 0x00100017, width 1
completed instructions: 262341 / 262343 / 262344 by signature route
```

The differing completed counts record the short-circuited comparisons, not a
divergent hardware state. All exact-marker cases preserve their respective
0..255 byte at `0x0c04` and still reach the same boundary.

The [Sega SCSP User's Manual](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf)
maps `0x100000..0x100017` to slot 0. Word offset `0x16` contains DISDL/DIPAN and
EFSDL/EFPAN; the observed odd-byte CLR targets its low EFSDL/EFPAN lane. The
follow-up [slot mixer model](SCSP_SLOT_MIXER_CONTROL.md) now accepts all 18
observed low-byte clears and exposes the next common boundary at DSP COEF
address `0x100700`. It does not infer synthesis, reset values, key state,
timing or audible output from those accesses.

Sound-ROM execution rises from 5% to 10% because the original program now has
an exhaustive unknown-state bridge and advances roughly eightfold to a common
documented-device boundary. Audio and SCSP remain 0%, overall HOTD1 remains
about 10%, and Gates A/B/C remain open.
