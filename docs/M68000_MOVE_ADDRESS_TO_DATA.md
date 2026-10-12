# MC68000 MOVE from address register to data register

The bootstrap translator supports the original MC68000 word and long forms of
`MOVE An,Dn`. Byte-sized address-register-direct sources remain rejected
because the architecture does not permit them.

## Architectural contract

The Motorola M68000 Family Programmer's Reference Manual lists address-register
direct among MOVE source effective addresses, with an explicit exception for
byte operations. MOVE copies the selected word or long to the data-register
destination. A word operation preserves the destination's upper 16 bits; a
long operation replaces all 32 bits. X is unaffected, N and Z reflect the
moved-width value, and V and C clear.

The native translation requires the complete source address register to be
known, updates only the architecturally selected data-register bits and their
known mask, and invokes no bus callback. An unknown source stops atomically as
undefined state.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
MOVE on printed pages 4-116 through 4-118.

## Original-program evidence

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `MOVE.L A3,D7` at
`0x00600378`. Translation of that instruction is CPU coverage evidence only;
it does not establish sound-board behavior.
