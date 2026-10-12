# Original MC68000 brief indexed effective addresses

Date: 2026-10-12. Scope: `(d8,An,Xn)` for CLR memory, MOVEA memory source,
MOVE memory to Dn, and MOVE Dn to memory.

## Architectural contract

The original MC68000 brief extension word selects one data or address index
register, a sign-extended word or long index, and a signed 8-bit displacement.
The effective address is the 32-bit sum of the address-register base, index and
displacement; the existing operand helpers independently mask each physical
bus transaction to 24 bits. A word index uses only its known low 16 bits and
sign-extends them. A long data index requires all 32 bits, while address-index
forms require the selected address register to be known.

Extension bits 10 through 8 are reserved on the original core. Encodings that
would request later-family scale or full-extension behavior remain explicitly
unsupported. The effective address is resolved before a destination register
is changed, preserving source/destination alias behavior. Existing strict
operand helpers retain alignment, read-before-write CLR, high-word-first MOVE
long transfers, condition codes and refused-transaction diagnostics.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the indexed effective-address mode and CLR, MOVE and MOVEA entries.

## Verification and original-program evidence

`tests/test_m68k_indexed_native.py` contains generated synthetic instructions
only. Three GCC/Clang UBSan tests cover every base and index register, data and
address indexes, word and long indexes, all signed 8-bit displacement
boundaries, all four instruction families and widths, aliases, exact values,
flags, transaction widths/order, unknown inputs, reserved encodings, invalid
helper arguments and truncated extension words.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains these four former stops:

- `CLR.B ($17,A5,D4.W)` at `0x00600344`;
- `MOVEA.L ($02,A3,D0.W),A4` at `0x00600394`;
- `MOVE.L D0,($04,A5,D1.W)` at `0x00601B7A`;
- `MOVE.W ($04,A0,D0.W),D0` at `0x006023B4`.

Supporting them expands reset-vector discovery from 307 instructions / 296
translated to 335 / 326. Two paths rejoin existing translated code and the
others advance to explicit stops at `0x00602066` and `0x006023D0`, reducing the
unsupported frontier from eleven sites to nine while adding thirty translated
instructions.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No source memory, peripheral result,
reset wiring or sound output is invented, and static graph reachability is not
presented as uninterrupted execution.
