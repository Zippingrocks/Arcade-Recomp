# MC68000 ADDI and NEGX data-register arithmetic

Date: 2026-10-12. Scope: byte, word and long `ADDI #imm,Dn` and
`NEGX Dn`.

## Architectural contracts

ADDI adds the encoded sized immediate to the selected low data-register byte,
word or long. NEGX computes zero minus the sized register value minus the
incoming X bit. Both preserve unselected upper register bits and set XNZVC at
the operation width.

ADDI sets X and C from unsigned carry and V from signed overflow. NEGX requires
a known X input, reports borrow in both X and C, and implements the instruction's
cumulative Z rule: a nonzero result clears Z, while a zero result retains the
previous Z value and knownness. This supports chained multi-precision negation
without inventing an unknown incoming flag. Both helpers require every selected
source bit to be known and reject invalid widths or registers before modifying
the arithmetic result. Neither form touches the bus.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the ADDI and NEGX instruction entries and condition-code definitions.

## Verification and original-program boundary

`tests/test_m68k_addi_native.py` and `tests/test_m68k_negx_native.py` contain
only generated synthetic instructions. Six GCC/UBSan tests cover all widths and
registers, every byte operand, wide boundary matrices, carry/borrow, signed
overflow, cumulative zero with known and unknown prior Z, extension decoding,
excluded effective addresses, partial register knownness and invalid helper
arguments.

The authenticated EPR-19720 sound chip has SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`. Its board-region reconstruction
word-swaps each stored pair; the reconstructed instruction at `0x00600412` is
`ADDI.W #$20,D0`. Raw chip bytes at that offset must not be decoded directly as
an instruction. ADDI support grows reset-vector discovery from 179 instructions
/ 172 translated to 183 / 176 and advances that branch to the still-unsupported
register-count logical shift at `0x00600422` (`LSR.L D0,D1`). Seven explicit
unsupported sites remain.

NEGX is synthetic architecture coverage in this batch and is not claimed as an
original-program discovery gain. Strict execution remains at 17 instructions
before the unknown SCSP byte read at `0x00100401`; the opt-in common-control
model remains at 18 before the unknown board byte write at `0x00400001`. No
device result, reset wiring or sound output was inferred.
