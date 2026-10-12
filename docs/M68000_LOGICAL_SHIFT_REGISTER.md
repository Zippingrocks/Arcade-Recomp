# MC68000 register-count logical shifts

Date: 2026-10-12. Scope: byte, word and long `LSL Dn,Dn` and `LSR Dn,Dn`.

## Architectural contract

The shift count is the count register's low six bits, allowing values from zero
through 63 independently of operand width. The selected destination byte, word
or long is shifted logically and unselected upper bits remain unchanged. N and
Z describe the sized result and V is cleared. For a nonzero count, the last bit
shifted out is copied to both C and X. A zero count clears C but preserves X and
its knownness.

The native helper requires the destination operand and the count register's low
six bits to be known before changing state. It handles aliased count and
destination registers from the same pre-instruction value, and gives defined
results for counts equal to or greater than the selected width. These register
forms do not touch the bus.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
LSL/LSR register forms and the shift/rotate condition-code definitions.

## Verification and original-program evidence

`tests/test_m68k_logical_shift_register_native.py` contains generated synthetic
instructions only. Three GCC/UBSan tests cover every width, direction, count and
destination register, all aliases, count masking, zero and beyond-width counts,
exhaustive byte operands/counts, X knownness, excluded shift families, unknown
inputs and invalid helper arguments.

The authenticated, word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `LSR.L D0,D1` at
`0x00600422`. Supporting the bounded logical register-count family grows
reset-vector discovery from 183 instructions / 176 translated to 188 / 182 and
removes this branch end, reducing explicit unsupported sites from seven to six.
The branch rejoins already translated control flow rather than exposing another
unknown instruction.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the unknown
board byte write at `0x00400001`. Arithmetic and static graph coverage do not
establish sound-board timing or output, and no device value was invented.
