# MC68000 non-updating memory-to-memory MOVE

Date: 2026-10-12. Scope: byte, word and long `MOVE <ea>,<ea>` between
non-updating address-indirect, displacement, absolute-short and absolute-long
memory operands.

## Architectural contract

MOVE reads the complete source operand before writing the same sized value to
the destination. N and Z describe that value, V and C are cleared, and X
preserves both value and knownness. Neither effective address updates an
address register in this bounded family.

Both register-based effective addresses must be known before any bus access.
Word and long operands require even addresses. Logical addresses reach the
physical bus independently through the 24-bit mask; long reads and ordinary
MOVE.L writes occur high word first. A refused transaction commits no CPU
state, flags, PC or completion count, while prior accepted bus transactions
remain observable. Updating, indexed and PC-relative forms remain outside this
step.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the MOVE instruction entry and effective-address definitions.

## Verification and original-program evidence

`tests/test_m68k_memory_to_memory_native.py` contains generated synthetic
instructions only. Three GCC/UBSan tests cover every width and address-register
pair, all supported source/destination extension combinations and ordering,
aliases, 24-bit wrap, exact read/write order and flags, unknown addresses,
alignment and every refused read or write cycle. The existing memory-load
boundary test now recognizes these newly supported destination forms.

The authenticated, word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains
`MOVE.B 3(A6),$0408(A5)` at `0x006019dc`, `0x00601b5e`, `0x00601b90` and
`0x00601bb6`. Supporting those sites expands reset-vector discovery from 255
instructions / 245 translated to 295 / 284. Four former stops are removed and
five deeper stops become reachable, so the explicit unsupported frontier grows
from ten to eleven while translated coverage gains 39 instructions. The new
stops remain explicit rather than being guessed through.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the unknown
board byte write at `0x00400001`. The translator does not invent source memory
or device data and does not claim these discovered branches execute during the
current bounded bootstrap.
