# MC68000 immediate bit test

Date: 2026-10-12. Scope: immediate `BTST #<data>,<ea>` for data
registers and non-updating address-indirect, displacement, absolute-short and
absolute-long memory operands.

## Architectural contract

BTST selects the immediate bit modulo 32 for a data-register destination and
modulo 8 for a memory destination. It does not modify the tested operand. Only
Z is changed: Z is set when the selected bit is clear and cleared when it is
set. X, N, V and C preserve both their values and knownness.

The selected data-register bit, or the memory source address and byte, must be
known before the instruction commits. Memory accesses use 24-bit physical
addresses. A refused read commits no flags, PC or completion count. Updating,
indexed, PC-relative and immediate destinations remain outside this bounded
form.

Primary source: [Motorola M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
the BTST instruction entry and effective-address definitions.

## Verification and original-program evidence

`tests/test_m68k_btst_immediate_native.py` contains generated synthetic
instructions only. Three GCC/UBSan tests cover immediate modulo behavior,
every data/address register, each supported effective-address form, partial
register knownness, all preexisting condition-code values and knownness,
excluded modes, truncated extensions, unknown addresses and refused reads.

The authenticated, word-swapped EPR-19720 board region (source chip SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`) contains `BTST #2,(A6)` at
`0x00601a50` and `BTST #0,(A6)` at `0x00601b2c`. Supporting those instructions
expands reset-vector discovery from 245 instructions / 237 translated to 255 /
245. Eight newly translated instructions expose four downstream stops at
`0x00601b3a`, `0x00601b5e`, `0x00601b90` and `0x00601bb6`, in addition to the
previously reachable unsupported sites. The explicit unsupported frontier
therefore grows from eight to ten; those stops are retained rather than
guessed through.

Strict execution remains at 17 instructions before the unknown SCSP byte read
at `0x00100401`; the opt-in common-control model remains at 18 before the unknown
board byte write at `0x00400001`. The translator does not invent either tested
memory byte or claim that these newly discovered branches execute during the
current bounded bootstrap.
