# MC68000 data-register subtraction

The bootstrap translator supports original MC68000 `SUB.B/W/L Dn,Dn`
instructions in the effective-address-to-data-register direction.

## Architectural contract

SUB subtracts the sized source from the sized destination, writes the result to
the destination, and preserves the unselected upper data-register bits for byte
and word operations. N and Z describe the sized result, V reports signed
overflow, C reports unsigned borrow, and X is set to the same value as C.

The native helper requires every selected source and destination bit to be
known, computes with explicitly bounded unsigned arithmetic, marks all five
arithmetic flags known, and stops atomically for unsupported arguments or
unknown operands. Register-direct SUB performs no bus access.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
SUB on printed pages 4-174 through 4-176.

## Original-program evidence

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `SUB.W D7,D6` at
`0x006003d4`. Translation of that instruction is CPU coverage evidence only;
it does not establish sound-board behavior.
