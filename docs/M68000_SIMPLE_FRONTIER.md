# MC68000 quick, bit, multiply, MOVE and PC-indexed frontier

Date: 2026-10-12. Scope: memory `ADDQ`, immediate memory `BSET`, register-source
`MULU.W`, immediate MOVE to non-updating or postincrement memory,
postincrement-source MOVE to non-updating memory, and PC-indexed `LEA`.

## Architectural contracts

Memory ADDQ performs a sized read-modify-write and sets XNZVC from the
addition. Immediate BSET operates on a byte memory destination, selects the
encoded bit modulo eight, writes the set result, and changes only Z according
to the bit's prior value. Neither helper treats refused device access as RAM;
flags and completion state commit only after the write succeeds.

MULU multiplies the unsigned low words of its source and destination data
registers into a 32-bit destination. N and Z describe the result, V and C
clear, and X preserves value and knownness. Both low-word operands must be
known, including the alias case.

Immediate MOVE now covers byte, word and long destinations through
address-indirect, postincrement, displacement, absolute-short and
absolute-long modes. Postincrement-source MOVE completes the source read and
increments that address register before evaluating/writing the non-updating
destination; this matters when both effective addresses use the same register.
MOVE retains the existing strict alignment, high-word-first long transfers,
NZVC updates and X preservation.

PC-indexed LEA uses the address of its extension word as the PC base, plus the
original-MC68000 signed byte displacement and sign-extended word or long data/
address index. Reserved later-core extension bits remain unsupported. LEA
touches no bus and preserves all flags.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the ADDQ, BSET, MULU, MOVE, LEA and effective-address entries.

## Verification and original-program evidence

`tests/test_m68k_simple_frontier_native.py` and
`tests/test_m68k_move_frontier_native.py` contain generated synthetic
instructions only. Seven GCC/Clang UBSan tests cover all widths and register
fields, quick and bit immediates, signed displacements, every supported memory
form, read-modify-write values/order, multiplication boundaries and aliases,
immediate and postincrement MOVE ordering including address-register aliases,
PC-indexed data/address and word/long indexes, exact flags, knownness,
exclusions and truncation. Earlier subset-boundary tests were updated only for
the forms deliberately admitted here.

The authenticated word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains these newly translated
sites:

- memory `ADDQ.W` at `0x006006F6`;
- immediate memory `BSET` at `0x00601B9C`;
- long immediate MOVE to displacement at `0x00601C2E`;
- `MULU.W D7,D0` at `0x00602066`;
- long immediate MOVE to postincrement at `0x006021D4`;
- byte postincrement-source MOVE to absolute-short at `0x006023D0`;
- PC-indexed LEA at `0x0060070A` and `0x00601C3E`.

Together they expand reset-vector discovery from 352 instructions / 344
translated to 386 / 380. The unsupported frontier falls from eight sites to
six while translated coverage gains thirty-six instructions. Four remaining
stops are MOVEM forms. The two PC-indexed LEAs honestly expose indirect JMP
sites at `0x0060070E` and `0x00601C42`; merely decoding those JMPs would not
identify their run-time targets, so no false fallthrough was added.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the
unknown board byte write at `0x00400001`. No source memory, peripheral result,
indirect branch target, reset wiring or sound output is invented.
