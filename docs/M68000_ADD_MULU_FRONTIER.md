# MC68000 ADD, SUB, MULU and bit-operation frontier

Date: 2026-10-12. Scope: byte/word/long register ADD, data-register ADD/SUB
to non-updating and brief-indexed memory, immediate-source MULU.W, immediate
BCLR on Dn, and immediate BSET on brief-indexed memory.

## Architectural contracts

Register ADD and both memory-destination arithmetic directions operate at the
encoded width and set XNZVC from the exact sized result. Memory destinations
perform a real read-modify-write: the source register is validated first, the
destination is read, then the result is written. Flags and instruction
completion commit only after the write succeeds. Brief indexed addresses use
the existing original-MC68000 data/address, word/long and signed-displacement
contract; reserved later-core extension bits remain unsupported.

MULU.W multiplies the immediate unsigned word by the destination's unsigned
low word, replaces the full destination with the 32-bit product, sets NZ,
clears VC and preserves X. Immediate BCLR selects a Dn bit modulo 32, records
its old state in Z and makes the selected result bit known zero. Indexed BSET
selects a memory bit modulo eight, performs a byte read-modify-write and changes
only Z. Unknown selected register bits and refused bus transfers fail closed.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
the ADD, SUB, MULU, BCLR, BSET and effective-address descriptions.

## Verification and original-program evidence

`tests/test_m68k_add_mulu_frontier_native.py` and the expanded
`tests/test_m68k_simple_frontier_native.py` contain generated synthetic
instructions only. Their GCC/Clang UBSan matrices cover every width and
register field, source/destination aliases, non-updating and brief-indexed
memory forms, data/address word/long indexes, arithmetic boundaries, exact
XNZVC, multiplication boundaries, bit modulo behavior, partial knownness,
transaction order, alignment, truncation, reserved encodings and refused
writes. All 124 MC68000 tests pass.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) now translates the exposed
register and memory arithmetic at `0x006020D8`, `0x00602272`, `0x006022B2` and
`0x00602314`, immediate MULU at `0x00602122`, BCLR at `0x006020DC`, indexed
BSET at `0x00602130`, and the deeper ADD/SUB memory sequence beginning at
`0x006020E0` and `0x0060213A`.

Reset-vector discovery expands from 708 instructions / 700 translated to 744 /
741, gaining 36 discovered and 41 translated instructions. The unsupported
frontier falls from eight sites to exactly three: `JMP (A1)` at `0x00600296`
and `0x0060070E`, and `JMP (A0)` at `0x00601C42`. Their run-time register
values are not established by static discovery, so no target or fallthrough is
invented.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. Static instruction coverage is not
sound playback, RAM initialization, reset wiring or cabinet fidelity.
