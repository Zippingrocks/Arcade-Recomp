# MC68000 data-register stores

Date: 2026-10-12. Scope: byte, word and long `MOVE Dn,<ea>` to address
indirect, displacement, absolute-short and absolute-long destinations.

## Architectural contract

MOVE writes the selected low byte, low word or full long data-register value
without changing either register class. X is preserved, N and Z describe the
transferred width, and V and C are cleared. Only source bits selected by the
operation must be known.

Indirect and displacement forms require a known destination address register.
Word and long destinations must be even. Bus addresses independently wrap to
24 bits; a long writes its high word first and its low word second. No CPU state
is committed when a write is refused, although a successfully accepted first
word of a long transfer remains observable. This is a strict diagnostic stop,
not an implementation of an MC68000 bus-error exception frame.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
MOVE on printed pages 4-116 through 4-118 and effective-address descriptions in
Section 2.

## Verification

`tests/test_m68k_move_data_to_memory_native.py` contains only generated
synthetic instructions. Three GCC/UBSan tests cover all three widths, every
source and destination-base register, all four non-updating destination forms,
signed extensions, 24-bit wrap, write order, partial source knownness, exact
flags, truncation, excluded updating modes, odd addresses and each refused bus
cycle. The batch deliberately does not broaden immediate or updating stores.

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `MOVE.W D0,(A4)` at
`0x0060040c`. Supporting the bounded architectural family grows reset-vector
discovery from 177 instructions / 170 translated to 179 / 172 and advances that
branch to the still-unsupported `NEGX.B D6` at `0x00600412`. Seven explicit
unsupported sites remain. Strict execution still completes 17 instructions
before the unknown SCSP byte read at `0x00100401`; the opt-in common-control
model completes 18 before the unknown board byte write at `0x00400001`. No
device result or sound-board behavior was fabricated.
