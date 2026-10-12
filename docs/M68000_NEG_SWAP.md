# MC68000 data-register NEG and SWAP

Date: 2026-10-12. Scope: byte, word and long `NEG Dn`, plus `SWAP Dn`.

## Architectural contracts

NEG computes zero minus the selected low byte, word or long of a data
register and preserves the unselected upper bits. It sets N and Z from the
sized result, V only for the most-negative input, and both C and X when the
input is nonzero. All five arithmetic flags become known when the selected
operand bits are known.

SWAP exchanges the upper and lower 16-bit halves of a data register. It sets
N and Z from the 32-bit result, clears V and C, and preserves both the value
and knownness of X. The bounded native helper requires the complete register
to be known. Neither instruction touches the bus, and invalid helper arguments
or unknown required input stop before committing architectural state.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the NEG and SWAP instruction entries and condition-code definitions.

## Verification and original-program evidence

`tests/test_m68k_neg_swap_native.py` contains generated synthetic instructions
only. Three GCC/UBSan and Clang/UBSan tests cover every register and width,
every byte input, representative word/long boundaries, all prior flag values,
upper-bit preservation, exact flags, SWAP half exchange, unknown input,
excluded encodings and invalid helper arguments.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `NEG.L D5` at
`0x00601B3A` and `SWAP D0` at `0x00601B74`. Supporting those sites expands
reset-vector discovery from 302 instructions / 291 translated to 307 / 296.
The two former stops advance to explicit unsupported instructions at
`0x00601B42` and `0x00601B7A`; eleven unsupported frontier sites remain while
translated coverage gains five instructions.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No source memory, peripheral result,
reset wiring or sound output is invented, and static graph reachability is not
presented as uninterrupted execution.
