# MC68000 postincrement and indexed MOVE frontier

Date: 2026-10-12. Scope: byte/word/long `TST (An)+` and
`MOVE (An)+,(d8,An,Xn)` using original-MC68000 brief index extensions.

## Architectural contracts

Postincrement TST reads the operand at the old address and increments only
after that complete read succeeds. Byte operations increment A7 by two;
otherwise the increment equals the operand width. TST sets NZ, clears VC and
preserves X.

MOVE evaluates its source effective address and completes the source read
before evaluating its destination effective address. Consequently, when the
postincrement source register is also the indexed destination base or address
index, destination calculation observes the incremented value. The brief
extension supports data or address indexes, sign-extended word or long index
values and a signed eight-bit displacement. Reserved later-core scale/full
format bits remain unsupported.

A refused source read commits no postincrement. Once the source read is
complete, its increment remains observable if destination address evaluation
or the destination write is refused. Flags and instruction completion commit
only after a successful write. This diagnostic contract exposes accepted bus
effects; it is not an invented MC68000 bus-error exception frame or restart.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
the TST, MOVE and effective-address descriptions.

## Verification and original-program evidence

The expanded `tests/test_m68k_tst_native.py` and
`tests/test_m68k_move_frontier_native.py` contain generated synthetic
instructions only. Eight GCC/Clang UBSan tests cover every operand width,
source and base register, A7 byte increments, data/address and word/long
indexes, signed displacements, base/index/source aliases, exact bus order,
flags, reserved extensions, truncation, unknown destination components,
alignment and source/destination refusals. The complete 119-test MC68000 suite
passes.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) translates five postincrement TST
sites at `0x00600278`, `0x006020C0`, `0x0060211A`, `0x006023A2` and
`0x00602410`, plus six indexed-destination MOVE sites at `0x00602238`,
`0x0060224C`, `0x0060228C`, `0x006022D6`, `0x006022F0` and `0x00602328`.

Reset-vector discovery expands from 581 instructions / 568 translated to 708 /
700, gaining 127 discovered and 132 translated instructions. The unsupported
frontier falls from thirteen to eight sites. Three are run-time indirect JMPs
whose targets remain unproven. The other five are a memory-destination ADD.L,
an immediate-source MULU.W and three register ADD.W instructions, providing a
bounded arithmetic target for the next pass.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No peripheral value, RAM content,
indirect target, reset wiring or sound output is invented.
