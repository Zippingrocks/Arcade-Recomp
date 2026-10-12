# Original-MC68000 MOVEM frontier

Date: 2026-10-12. Scope: word/long register-list stores through `(An)` and
`-(An)`, plus word/long register-list loads through `(An)+`.

## Architectural contracts

The implementation follows Motorola's original-core rules rather than using
later 68020 behavior. A control-mode store visits the encoded register list in
`D0` through `D7`, then `A0` through `A7` order. A predecrement store uses the
reversed mask encoding and transfer order, `A7` through `A0`, then `D7` through
`D0`, decrementing before each operand. If the predecrement base register is
in the list, the MC68000 stores its initial value; later family members differ.

A postincrement load visits `D0` through `D7`, then `A0` through `A7`. Word
loads sign-extend to 32 bits. If the postincrement base register itself is in
the list, the memory value is ignored and the register retains the updated
effective address. MOVEM does not change condition codes.

Every word transfer uses the ordinary strict bus callbacks; long transfers
remain high-word first. Source knownness is checked before a store starts.
Completed operands and postincrements remain observable if a later device
transaction is refused, while the refused operand and instruction completion
do not commit. No unimplemented addressing mode is widened into a convenient
substitute.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
the MOVEM instruction and effective-address descriptions.

## Verification and original-program evidence

`tests/test_m68k_movem_native.py` contains generated synthetic instructions
only. Four GCC/Clang UBSan tests cover both widths, every base register, empty,
sparse and full masks, both store orders, original-MC68000 base-in-list rules,
word sign extension, exact transfer addresses and values, flag preservation,
decoder exclusions, truncation and a refused postincrement load.

The complete 117-test MC68000 suite passes. The authenticated word-swapped
EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) translates these MOVEM sites:

- `MOVEM.L (A1)+,...` at `0x00601A84`;
- `MOVEM.L ...,-(A2)` at `0x00601BEE`;
- `MOVEM.L ...,-(A7)` at `0x006023D8` and `0x006023EE`.

Those four instructions expand reset-vector discovery from 386 instructions /
380 translated to 581 / 568. This is a gain of 195 discovered and 188
translated instructions, not a claim that those paths can execute without
real RAM and devices. The larger graph honestly exposes thirteen unsupported
sites: five postincrement TSTs, six postincrement-source memory-to-memory
MOVEs, and the two existing run-time indirect JMPs. The JMP targets remain
unknown and no false static successors were added.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No peripheral value, RAM content,
indirect target, reset wiring or sound output is invented.
