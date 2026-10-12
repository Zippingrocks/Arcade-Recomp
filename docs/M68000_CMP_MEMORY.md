# MC68000 non-updating memory-source CMP

Date: 2026-10-12. Scope: byte, word and long `CMP <ea>,Dn` from
non-updating address-indirect, displacement, absolute-short and absolute-long
memory sources.

## Architectural contract

CMP reads the sized source and computes the condition codes for the low sized
destination data-register value minus that source without writing either
operand. N, Z, V and C describe the sized subtraction, including signed
overflow and unsigned borrow. X preserves both value and knownness.

The sized destination and any source address register must be known before a
bus transaction. Word and long sources require even addresses. Physical bus
addresses wrap independently to 24 bits and long reads occur high word first.
A refused read commits no flags, PC or completion count, while an accepted
first word of a subsequently refused long read remains observable. Updating,
indexed, PC-relative, immediate and register sources remain outside this
bounded form.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the CMP instruction entry and effective-address definitions.

## Verification and original-program evidence

`tests/test_m68k_cmp_memory_native.py` contains generated synthetic
instructions only. Three GCC/UBSan tests cover all widths, registers and
supported source forms, extension values, address wrap, subtraction results
and flags, X preservation, operand immutability, unknown state, alignment,
truncation, exclusions and every refused read cycle.

The authenticated, word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains
`CMP.B $0EFA.W,D0` at `0x006006d8` and `CMP.W (A0),D0` at `0x006023ac`.
Supporting those sites expands reset-vector discovery from 295 instructions /
284 translated to 302 / 291. The two former stops are replaced by two deeper
explicit stops, leaving the unsupported frontier at eleven while translated
coverage gains seven instructions.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the unknown
board byte write at `0x00400001`. No source memory or device value is invented,
and static graph reachability is not presented as uninterrupted execution.
