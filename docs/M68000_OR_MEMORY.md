# MC68000 non-updating memory-source OR

Date: 2026-10-12. Scope: byte, word and long `OR <ea>,Dn` from address
indirect, displacement, absolute-short and absolute-long sources.

## Architectural contract

OR reads the sized memory source, combines it with the selected low destination
data-register byte, word or long, and preserves unselected upper destination
bits. N and Z describe the sized result, V and C are cleared, and X preserves
both value and knownness.

The destination operand and any source address register must be known before a
bus transaction. Word and long sources require even addresses. Physical bus
addresses wrap independently to 24 bits and long reads occur high word first.
A refused read commits no destination, flags, PC or completion count, while an
accepted first word of a subsequently refused long read remains observable.
Updating, indexed, PC-relative, immediate and register sources remain outside
this bounded form.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the OR instruction entry and effective-address definitions.

## Verification and original-program evidence

`tests/test_m68k_or_memory_native.py` contains generated synthetic instructions
only. Three GCC/UBSan tests cover all widths and register fields, every supported
source form, address extensions and wrap, long-read order, result and XNZVC,
partial knownness, excluded modes, odd addresses and each refused read cycle.

The authenticated, word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains
`OR.B $00608068.L,D0` at `0x006001f0`. Supporting the bounded family expands
reset-vector discovery from 198 instructions / 193 translated to 245 / 237.
That path exposes four previously unreachable stops at `0x006019dc`,
`0x00601a50`, `0x00601a64` and `0x00601b2c`; explicit unsupported sites
therefore rise from five to eight while the reachable translated frontier grows
by 44 instructions. Newly exposed stops are retained, not guessed through.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the unknown
board byte write at `0x00400001`. The translator does not provide a value for
the OR source address or claim the newly discovered paths execute continuously.
