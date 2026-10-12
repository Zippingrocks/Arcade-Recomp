# Intel KB MOVR: exact native real-format moves

Implemented: `MOVR` **6C9h**, decoded and emitted as native AOT operations.
The [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pp. 11-86–11-87, 12-10 and 12-15, specifies conversion between
binary32 GPR values and extended80 FP registers. FP-to-FP moves retain
extended precision; GPR-to-GPR moves retain binary32 representation.

The supported subset is canonical finite normal values and signed zeros.
FP-to-GPR conversion must be exactly representable as normal binary32
or signed zero. Subnormals, noncanonical extended encodings, NaNs,
infinities, overflow/underflow and inexact conversion deliberately stop.
These are diagnostic limitations, not architected Intel fault delivery.
Floating literals remain unsupported. No host floating arithmetic is used.

The helper validates register indices and source FP definedness before
mutation, captures aliased sources, and only establishes destination FP
definedness after success. Exact moves do not depend on rounding mode;
existing AC flags, rounding/normalizing fields and knownness are preserved.
As elsewhere in the i960 runtime, GPR values lack per-register definedness;
this does not establish their physical reset contents.

## Encoding cross-check

MOVR 6C9h and MOVRL 6D9h agree between the Intel manual and the
[GNU assembler's historical i960 opcode table](https://gnu.googlesource.com/binutils-gdb/+/refs/tags/gdb-7.8-branchpoint/include/opcode/i960.h).
The early Intel manual instead prints **6E9h** for MOVRE, whereas that
assembler uses **6E1h**. Existing MOVRE support remains at 6E1h; this change
does not claim that discrepancy is resolved or silently accept both
opcodes. No third-party implementation is copied. Tests distinguish all
three existing move opcodes and preserve the current 6E9h stop.

## Evidence and limits

`tests/test_i960_movr_native.py` contains five ROM-free tests with
3,058 exact rational-oracle vectors, three AC profiles, signed zeros,
all normal binary32 exponents, register aliases, full extended precision,
unknown/reset FP state, reserved encodings, bounds and atomic refusals.
Native C++ runs under GCC/Clang when available with UBSan.

Private original `hotdo` instruction sites at **0x11FC** and **0x1394**
passed **18,348** isolated native checks using synthetic CPU state under
GCC/UBSan. The reconstructed main-CPU region was authenticated by SHA-256
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
No original bytes or game-derived C++ are published.

The two-root static graph (0x5F0 and 0x6B0, limit 16,384) now has
3,201 candidate instructions, of which 3,199 translate. Its newly exposed
stops are MULRL 79Ch at 0x1200 and CVTZRIL 6C3h at 0x1398. Static discovery
and isolated synthetic-state execution are not continuous game execution
or original-board reference evidence. Authentic serial RX/status, CPU
faults/interrupts/rounding and platform gameplay remain unresolved.

Estimated CPU floating progress stays **40%**, native CPU **55%**, and
overall original HOTD1 **10%**. Gates A/B/C remain open.

```sh
python -m unittest discover -s tests -p test_i960_movr_native.py -v
```
