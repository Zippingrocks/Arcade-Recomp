# Intel KB floating operand encoding correction

This is a correctness correction, not an additional fidelity percentage.
Previous decoder/emitter code incorrectly selected FP source registers with
instruction bits 5/6 (`0x20`/`0x40`). The corresponding synthetic instruction
builders repeated the mistake. Those earlier FP-source native test results
**did not validate legal Intel instruction encodings**. They exercised the
runtime arithmetic/data-movement helpers through invalid synthetic words.
Earlier claims of verified FP-source AOT execution must be read with this
correction; the append-only progress history is not rewritten.

The primary [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
Appendix B, printed B-1–B-3 (PDF pages 373–375, one-based), gives:

| Instruction field | Documented function |
| --- | --- |
| Bits 5 and 6 | Reserved zero |
| M1, bit 11 | Selects the source 1 operand bank |
| M2, bit 12 | Selects the source 2 operand bank |
| M3, bit 13 | Selects the floating destination bank |

For a real source, a clear M bit selects a GPR. A set M bit selects fp0–fp3
for operand indices 0–3, literal +0.0 for index 16, or literal +1.0 for
index 22; other indices are reserved. Floating literals remain explicitly
unsupported here. Integer sources in CVTIR and SCALER retain their distinct
integer-literal meaning when M1 is set. The unused source 2 field in unary
instructions retains the emitter's conservative canonical-encoding check.

## Corrected implementation and proof

The decoder now applies reserved-bit refusal across all fourteen supported
floating instruction names. It decodes real sources through M1/M2, including
currently unsupported arithmetic FP-register forms, without mislabeling
them as integer literals. Native FP sources are corrected for CVTZRI,
LOGBNR, MOVR, MOVRL, MOVRE, CPYSRE and CPYRSRE. Existing runtime numeric
algorithms are unchanged; the new CVTZRIL implementation uses the correct
encoding from its first test.

The affected six synthetic FP test builders and one IAC/reset fixture now
use legal source modes. A separate Appendix-B test table checks FP source
indices, literal/reserved refusals, integer-source exceptions and all three
nonzero combinations of reserved bits for each floating family. These
checks do not use the decoder's opcode table as their oracle.

Original GPR-source evidence remains distinct: the original MOVR checks at
0x11FC/0x1394 and earlier GPR-only FP instruction checks did not use the
incorrect source mode. Their original words were not altered to make this
correction pass. Newly verified original FP-source CVTZRIL checks are
described in [I960_CVTZRIL.md](I960_CVTZRIL.md).

All 170 i960 tests passed GCC/UBSan after correction. This supersedes the
earlier invalid-encoding FP-source synthetic evidence; it is still not an
independent hardware trace. MOVRE's separately documented 6E1/6E9 opcode
source discrepancy remains unresolved and its opcode is unchanged.
Estimated floating progress stays 40%, CPU 55%, overall original HOTD1 10%.
