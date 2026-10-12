# MC68000 LEA address-register displacement support

The bootstrap translator supports the original MC68000
`LEA (d16,An),Am` encoding. This is deliberately limited to the documented
address-register-indirect-with-displacement control addressing mode needed by
the authenticated HOTD1 sound program.

## Architectural contract

The Motorola M68000 Family Programmer's Reference Manual defines LEA as loading
the effective address into all 32 bits of the destination address register and
leaving condition codes unchanged. Its addressing-mode chapter defines
`(d16,An)` as the source address register plus a 16-bit displacement sign
extended to 32 bits. LEA computes that address; it does not read the memory at
the address.

The native implementation therefore requires a known source address register,
adds the sign-extended displacement with 32-bit wraparound, marks the complete
destination address register known, preserves SR and SR-known state, and never
invokes a bus callback. An unknown source stops atomically as undefined state.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
sections 2.2.6 (address register indirect with displacement) and 4 (LEA).

## Original-program evidence

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains newly translated LEA
sites at `0x00600242`, `0x0060044c`, and `0x006021b6`. This is instruction
coverage evidence only; it does not claim that later sound-board I/O behavior
has been replicated.
