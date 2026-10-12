# MC68000 ADDA data-register sources

The bootstrap translator supports original MC68000 `ADDA.W/L Dn,An`
instructions.

## Architectural contract

ADDA adds its source to the entire 32-bit destination address register and
leaves every condition code unaffected. The word form sign-extends its low
16-bit source to 32 bits before addition; the long form uses all 32 source
bits. The result wraps naturally at 32 bits.

The native translation requires the selected source data-register bits and the
complete destination address register to be known. It modifies only the
destination address register, performs no bus access, and stops atomically as
undefined state if either operand is unavailable.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
ADDA on printed pages 4-7 and 4-8.

## Original-program evidence

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `ADDA.L D0,A1` at
`0x006003c2`. Translation of that instruction is CPU coverage evidence only;
it does not establish sound-board behavior.
