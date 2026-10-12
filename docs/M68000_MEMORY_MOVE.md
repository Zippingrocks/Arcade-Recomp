# Native MC68000 memory-to-memory postincrement MOVE

Date: 2026-10-11. Scope: byte, word and long `MOVE (An)+,(Am)+`
translated ahead of time from fixed instructions. This does not add an
interpreter, sound RAM, SCSP behavior or a permissive board bus.

## Primary architecture source

Motorola's [M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
printed 2-6 and 4-116 through 4-118, defines both postincrement effective
addresses as legal for MOVE. It specifies source-to-destination evaluation,
increments of one, two or four bytes after a byte, word or long operand is
used, and the special two-byte byte increment for A7. MOVE preserves X, sets
N and Z from the transferred value, and clears V and C.

The native subset performs explicit byte or word callbacks. An ordinary
longword is read and written as the high word at the lower address followed
by the low word. Predecrement and CLR.L have different transfer rules and do
not use this helper. Address-register arithmetic remains 32-bit while every
physical transaction is independently masked to the MC68000's 24-bit bus.
Odd word/long operands stop before their first transaction.

## Diagnostic fault boundary

Source is evaluated before destination. A postincrement is committed after
that operand's complete diagnostic bus transfer, so a refused source changes
neither pointer and a refused destination retains a completed source
increment. A rejected second longword cycle retains the first cycle's
external side effect. This makes the strict runtime observable and retry-safe;
it is not a claim to reproduce an MC68000 bus-error exception frame,
instruction prefetch or restart microstate. Unknown address registers and
unsupported control state still stop without inventing an address.

When source and destination name the same register, destination observes the
source's completed increment. Consequently a byte transfer through A7 advances
twice by two bytes, while an ordinary register advances twice by operand size.

## Verification and original-byte evidence

Three ROM-free native tests cover every size and all 64 source/destination
register pairs, aliasing, A7 byte alignment, flags, exact longword callback
order, 24-bit addresses, unknown pointers, odd addresses and rejection of
each read/write word cycle. The focused GCC/UBSan run and all 42 MC68000 tests
pass. The full authenticated generated sound source also passes strict Clang
syntax checking at `-O2 -Wall -Wextra -Werror`.

The original sound chip authenticates as SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`. Its instruction at `0x60035E` is
`0x22D8`, `MOVE.L (A0)+,(A1)+`, inside a ROM-to-address-zero copy loop. Adding
the real instruction family grows the reset-vector static graph from 88/77
discovered/translated sites to 90/80 and removes `0x60035E` from the
unsupported list. Ten unsupported sites remain; the newly exposed path ends
at RTS rather than guessing a return target.

Continuous execution is deliberately unchanged: strict mode completes 17
instructions before the unimplemented SCSP read at `0x100401`; opting into
the separately documented SCSP common-control subset completes 18 before the
unimplemented board write at `0x400001`. The copy loop is not reached without
real earlier device behavior, and this work does not install fake RAM to make
it run. Sound CPU remains 5%, audio remains 0%, and overall original HOTD1
remains 10%. Gates A/B/C remain open.
