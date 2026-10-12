# MC68000 SUBI, memory-source ADD and memory SUBQ

Date: 2026-10-12. Scope: byte, word and long `SUBI #imm,Dn`, non-updating
memory-source `ADD <ea>,Dn`, and non-updating memory-destination
`SUBQ #1..8,<ea>`.

## Architectural contracts

SUBI subtracts its sized immediate from the low byte, word or long of a data
register and preserves unselected upper bits. Memory-source ADD reads its
operand before adding it to the sized destination data register. Both require
the selected destination bits to be known before committing state. SUBQ memory
performs a real read-modify-write transaction; it never treats an unimplemented
device as RAM.

All three set X and C from carry or borrow, N and Z from the sized result, and
V from signed overflow. Successful byte/word register operations preserve
upper bits. Word and long memory operands require even addresses, long reads
and ordinary writes transfer the high word first, and each physical bus cycle
wraps independently to 24 bits. A refused transaction commits no flags, PC or
completion count, while already accepted diagnostic bus effects remain
observable.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the ADD, SUBI and SUBQ instruction entries and condition-code definitions.

## Verification and original-program evidence

`tests/test_m68k_arithmetic_frontier_native.py` contains generated synthetic
instructions only. Four GCC/Clang UBSan tests cover every width and data
register, exhaustive byte SUBI operands, wide signed/unsigned boundaries,
all quick immediates, indirect/displacement/absolute memory forms, extension
decoding, 24-bit addresses, long transaction order, read-modify-write results,
exact flags, excluded modes, invalid helpers and truncation.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains:

- `SUBQ.B #1,$0ECC.W` at `0x006006E2`;
- `SUBI.L #$00000200,D5` at `0x00601A64`;
- `ADD.L $14(A6),D5` at `0x00601B42`.

Supporting those sites expands reset-vector discovery from 335 instructions /
326 translated to 352 / 344. The ADD path rejoins existing translated code;
the other paths advance to explicit stops at `0x006006F6` and `0x00601A84`.
The unsupported frontier falls from nine sites to eight while translated
coverage gains eighteen instructions.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No source memory, peripheral result,
reset wiring or sound output is invented, and static graph reachability is not
presented as uninterrupted execution.
