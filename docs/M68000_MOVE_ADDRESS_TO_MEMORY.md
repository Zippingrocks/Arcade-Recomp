# MC68000 address-register stores

Date: 2026-10-12. Scope: word and long `MOVE An,<ea>` to address
indirect, displacement, absolute-short and absolute-long destinations.

## Architectural contract

Address-register direct is a legal source for word and long MOVE, but not byte
MOVE. The selected low word or full long value is written without changing the
source or destination address registers. MOVE preserves X, sets N and Z from
the transferred width, and clears V and C.

The native path requires the source address register and any destination base
register to be known before touching the bus. Word and long destinations must
be even. A long write performs the high-word transaction first and the low-word
transaction second, with each physical address independently wrapped to the
MC68000's 24-bit bus. A refused write leaves PC, completion count and condition
codes uncommitted, while an already accepted first long-word transaction remains
observable. This is diagnostic stop behavior, not a reconstructed 68000 bus
error exception frame.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
MOVE on printed pages 4-116 through 4-118 and effective-address descriptions in
Section 2.

## Verification

`tests/test_m68k_move_address_to_memory_native.py` uses generated synthetic
instructions only. Three GCC/UBSan tests cover both widths, every source
register, every indirect/displacement destination register, both absolute
forms, source/destination aliasing, signed extensions, 24-bit wrap, bus order,
X knownness preservation, byte exclusion, truncation, unknown inputs, odd
addresses and first/second-cycle refusal.

The authenticated EPR-19720 image (SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains
`MOVE.L A4,$0EE4.W` at `0x006003f4`. Supporting the bounded architectural form
grows reset-vector discovery from 172 instructions / 165 translated to 177 / 170
and advances that branch to the still-unsupported `MOVE.W D0,(A4)` at
`0x0060040c`. Seven explicit unsupported sites remain. Strict execution still
completes 17 instructions before the unknown SCSP byte read at `0x00100401`;
the separately opted-in common-control model completes 18 before the unknown
board byte write at `0x00400001`. No device response or sound-board behavior
was inferred.
