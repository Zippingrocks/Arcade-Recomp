# MC68000 postincrement memory loads

The bootstrap translator supports original MC68000
`MOVE.B/W/L (An)+,Dn` instructions.

## Architectural contract

MOVE reads the sized source operand, writes the corresponding low byte, word or
long of the destination data register, preserves unselected upper destination
bits, leaves X unchanged, sets N and Z from the moved-width value, and clears V
and C. Address-register postincrement advances after the operand transfer by
the operand size, except that byte access through A7 advances by two to keep
the stack pointer even.

The native diagnostic model requires a known source address, performs the same
24-bit big-endian bus transactions as other memory reads, and commits the full
32-bit address-register increment only after the complete read succeeds.
Refused reads preserve CPU registers and flags while already accepted provider
transactions remain observable. This is deliberately not a physical BERR
exception/restart model.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
MOVE on printed pages 4-116 through 4-118 and postincrement addressing in
section 2.2.4.

## Original-program evidence

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `MOVE.B (A1)+,D0` at
`0x0060038a`. Translation of that instruction is CPU coverage evidence only;
it does not establish sound RAM or device behavior.
