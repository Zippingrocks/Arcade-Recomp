# Intel i960KB SQRTR: bounded exact native square root

## Primary specification and supported scope

The [Intel 80960KB Programmer's Reference Manual, 270567-001](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pages **11-115/116**, defines `SQRTR` opcode `688h`, its square-root
operation, signed-zero results and floating exceptions. Printed pages
**12-12..14** specify operand/destination formats and precision. Appendix B
defines the register-mode fields: M1 selects a floating source, M3 a floating
destination; bits 5/6 are reserved, not FP selectors.

`runtime/i960_fp_sqrt_exact.hpp` implements canonical finite positive normal
inputs whose square roots are exactly representable normal results, plus
positive and negative zero. GPR operands contain binary32; FP operands retain
the full extended80 significand. All four GPR/FP source/destination combinations
are native AOT operations. Source/destination aliases are supported.

The implementation uses only portable C++17 integer operations. It does not
invoke host floating arithmetic, `sqrt`, a compiler-specific 128-bit type, an
emulator, or copied third-party implementation code.

## Exactness argument

Write the nonzero input as `S * 2^k`, with its integer significand `S`. Removing
all powers of two from `S` leaves an odd integer and adjusts `k` without changing
the value. Its square root is a dyadic rational exactly when `k` is even and
the remaining odd integer is a perfect square. Otherwise no binary destination
can represent the exact result.

The significand occupies at most 64 bits, so its integer root fits in 32 bits.
A fixed 32-step descending trial-bit search computes the floor root. Every
trial is at most `2^32-1`, and every trial square therefore fits `uint64_t`.
An exact-square check rejects a nonzero remainder. The result is normalized,
then checked against the destination's precision and normal exponent range.
Shifts are bounded to 0..63; the implementation never shifts by a host-word
width or computes a signed overflowing product.

An extended input can have an exact square root requiring 25..32 significant
bits. Such a result succeeds in an FP register and explicitly stops when a
binary32 GPR destination would require rounding. FP-to-GPR range overflow or
underflow also stops.

## Refusal and state contract

Negative nonzero inputs, subnormal/noncanonical values, infinities and NaNs,
irrational/inexact results, and out-of-normal-range results stop explicitly.
Floating literals, invalid indices, reserved bits and noncanonical unused
operand fields remain untranslated. `SQRTRL` (`698h`) is not implemented.

Unknown FP sources remain unknown and stop; reset does not silently establish
them. Existing GPR reset-value knownness limitations are unchanged. No
destination, IP, condition code, AC flag, AC-knownness bit or other
architectural data changes before all checks succeed. Only stop diagnostics
change on refusal. A successful FP write establishes that destination's
knownness. Negative zero retains its sign in either destination format.
The generated-step pending-integer-overflow guard remains in force.

Exact normal/zero results need no choice of rounding direction and preserve
existing AC flags. This is **not** implementation of rounded results, masked
exception results/flags, architected floating-fault delivery, or CPU timing.

## Verification, October 11, 2026

`tests/test_i960_sqrtr_native.py` adds six ROM-free tests:

- 3,098 integer-root cases checked against Python's unbounded `math.isqrt`,
  including near-perfect squares and the maximum 64-bit input;
- 1,730 binary32 vectors across all four endpoint modes and four AC profiles;
- 392 extended80 vectors, including exact roots with more than 24 significant
  bits, exponent/range boundaries, and partially unknown AC state;
- aliases, register limits, both zero signs, undefined/special/negative values,
  reset invalidation, invalid encodings and pending-fault refusal.

The numeric oracle uses `Fraction` and separate unbounded integer roots of its
reduced numerator and denominator, independently of the runtime's
odd-significand decomposition. Six tests pass under GCC with UBSan and strict
warnings. The same six harnesses pass Clang 19 strict syntax checking; that
check is **not** a Clang execution result. The shared reserved-bit/FP-operand
regressions also include `SQRTR`. PR CI/full-suite evidence is tracked in the
parent change's progress review.

Two previous MULRL test-harness portability defects were corrected without
weakening warnings: helper-only harnesses now exercise the generated `step`,
and nested loop bodies use braces. All six MULRL tests pass GCC/UBSan again;
their strict Clang syntax checks also pass.

## Private original-instruction evidence and remaining blockers

The authenticated original `hotdo` main CPU image, SHA-256
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`, contains
`SQRTR g6,g4` at `0x1204`. That exact instruction passed **6,920 isolated
synthetic-state checks** under GCC/UBSan. The private reproducibility script is
`build/hotd1/sqrtr_site_probe.py`; ROM-derived generated C++ exists only in a
temporary directory. No game bytes, generated game code or assets are public.

The same bounded two-root graph (`0x5F0`, `0x6B0`; limit 16,384) grows from
**3,242 candidates / 3,241 translations** to **3,248 / 3,247**. It now stops at
`0x121C`, extended opcode `79Fh` (`ADDRL`). This graph is **not fully
translatable**, and supported opcodes can still stop on unsupported runtime
values. These are isolated instruction and static-analysis results, not a
continuous original boot, arcade-reference validation or measured FPS gain.

Authentic Sega 315-5649 RX/status, rounded floating arithmetic/faults,
interrupt delivery, Model 2C geometry/video/audio and gameplay remain open.
Subjective estimates remain **CPU floating 40% → 40%, CPU 55% → 55%, overall
original HOTD1 10% → 10%**. Gates A/B/C remain open.
