# Intel KB CVTZRIL: exact signed 64-bit conversion

Implemented: native AOT `CVTZRIL` **6C3h** for exactly integral, in-range
binary32 GPR or canonical extended80 FP-register input, including both
signed zeros. The signed result occupies an even-aligned GPR pair with the
low 32 bits in the first register. All of `[-2^63, 2^63-1]` is supported
when the input format represents the value exactly.

The [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pp. 11-50–11-51 and 12-16, defines truncation toward zero and the
64-bit integer destination. The long suffix describes the integer result,
not a binary64 GPR source. A binary64 input first requires MOVRL into an
FP register. Appendix B supplies the correct M1 FP-source selection;
see the [encoding correction](I960_FP_OPERAND_ENCODING.md).

The bounded implementation uses unsigned integer significands, checked
exponents and shifts. Negative results use unsigned two's-complement
subtraction, including INT64_MIN without signed overflow. Both result
halves are committed only after complete validation; source aliases with
either half are captured first. AC flags/knownness and source FP state are
preserved, and the generated stepper retains its pending-overflow guard.

Fractional inputs, noncanonical/special values and out-of-range integers
stop explicitly. The helper does not deliver architected overflow faults,
saturate the pair, or claim full rounding/exception support. Unknown FP
sources and reserved/unsupported operand forms stop without writing either
destination half or advancing IP. No host floating-point runtime arithmetic
is used, and GPR reset-value knownness remains an existing CPU limitation.

## Evidence

Four ROM-free native tests cover 1,338 extended80 vectors, 1,535 binary32
vectors, three AC profiles, signed range boundaries, discarded fraction
bits, aliases, FP reset/unknown state and direct-helper bounds. Python
unbounded integers and rational values provide the expected results.
Tests compile under GCC/Clang when available with UBSan.

Private original `hotdo` sites **0x1398, 0x13C8 and 0x13F8** passed
**12,042** isolated native checks using the same synthetic input/control
matrix under GCC/UBSan. Main-CPU SHA-256 is
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
Original words and generated game C++ remain private.

Two-root static discovery at 0x5F0/0x6B0 (limit 16,384) now finds 3,241
candidate instructions and translates 3,240. The remaining discovered
unknown is MULRL 79Ch at 0x1200. This is not exhaustive program coverage,
continuous startup or cabinet-reference evidence. Authentic serial input,
fault/interrupt delivery, rounding and platform gameplay remain unresolved.

Estimated floating progress stays **40%**, CPU **55%**, overall original
HOTD1 **10%**; Gates A/B/C remain open.

```sh
python -m unittest discover -s tests -p test_i960_cvtzril_native.py -v
python -m unittest discover -s tests -p test_i960_fp_operand_encoding.py -v
```
