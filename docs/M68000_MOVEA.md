# Native MC68000 MOVEA source modes

Date: 2026-10-12. Scope: word/long MOVEA from data registers, address
registers, non-updating address indirect, displacement, absolute short/long
and immediate operands. Instructions remain ahead-of-time translated; there
is no runtime opcode decoder or permissive device fallback.

## Primary architecture source

Motorola's [M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
printed 4-119 through 4-120, defines MOVEA for word and long operands. Every
implemented source form appears in its effective-address table. Word values
are sign-extended to 32 bits, long values are copied unchanged, and condition
codes are not affected. Byte MOVEA, updating, predecrement, indexed and
PC-relative source forms remain unsupported in this bounded extension.

Memory sources use the existing strict operand reader: byte callbacks cannot
silently satisfy word cycles, long operands read the high word then the low
word, odd addresses stop before a bus callback, and a refused second word
retains the first read's external side effect without modifying the
destination address register. Address arithmetic is 32-bit; each physical bus
transaction is separately masked to 24 bits. Unknown source registers stop
instead of supplying a guessed value.

## Verification and original-byte evidence

Three ROM-free tests cover both sizes, every source/destination register,
extension lengths, word sign extension, immediate and absolute values,
condition-code preservation, address wrapping, each memory word refusal,
alignment, unknown inputs and explicit unsupported-mode boundaries. All 45
MC68000 tests pass under GCC/UBSan. The authenticated generated sound source
also passes strict Clang syntax checking at `-O2 -Wall -Wextra -Werror`.

The original sound chip authenticates as SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`. This extension translates four
previously blocked original sites:

- `0x600218`: `0x204D`, `MOVEA.L A5,A0`;
- `0x600372`: `0x2679`, absolute-long memory to A3;
- `0x60045C`: `0x227C`, immediate long `0x00002000` to A1;
- `0x600492`: `0x2079`, absolute-long memory to A0.

The reset-vector static graph grows from 90/80 to 108/100
discovered/translated sites. Eight unsupported sites remain. The newly exposed
stops include `ADDQ.B #8,D2` at `0x600228` and `MOVE.L A3,D7` at `0x600378`;
they are retained as real next work rather than skipped.

Continuous execution remains unchanged: strict mode completes 17 instructions
before the unimplemented SCSP read at `0x100401`; the documented SCSP-control
opt-in completes 18 before the unimplemented board write at `0x400001`. This
work neither supplies those responses nor claims cabinet reset, timed audio or
physical-bus validation. Sound CPU remains 5%, audio remains 0%, and overall
original HOTD1 remains 10%. Gates A/B/C remain open.
