# Intel i960KB ADDRL: exact native long-real addition

## Specification and scope

The [Intel 80960KB Programmer's Reference Manual, 270567-001](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed **11-8/9**, specifies `ADDRL` (`79Fh`), even GPR-pair alignment,
addition, signed-zero behavior and exceptions. Printed **3-11** defines the
rounding modes; **12-7..14** defines formats and destination precision;
Appendix B defines the M1/M2/M3 register selectors and reserved bits.

`runtime/i960_fp_add_long_exact.hpp` implements all eight combinations of
binary64 GPR-pair and extended80 FP source/destination registers. Canonical
normal inputs and signed zeros are accepted when the result is an exact
normal number or signed zero in the destination format. The implementation
is general register arithmetic, not an original-address special case.

The original MULRL source parser is now shared in
`runtime/i960_fp_long_operand.hpp`. Both instructions apply the same index,
alignment, FP-knownness and canonical-format checks. This extraction does not
broaden MULRL behavior.

## Portable arithmetic and cancellation

Each nonzero operand is represented as a normalized 64-bit integer
significand times a power of two. Addition/subtraction uses two unsigned
64-bit limbs, explicit carry/borrow and alignment without discarded bits.
The larger-magnitude source is ordered first. Source aliases are captured
before any destination write.

An exponent gap of at most 64 fits in the two limbs. The boundary of 64 is
important: `1 - 2^-64` is exactly representable with 64 significant bits.
For a gap greater than 64, a nonzero smaller source forces more than 64
significant result bits even for opposite-sign subtraction. Such results
stop, not round. Range checks also distinguish out-of-normal-range results.
Normalization rejects every nonzero bit that destination narrowing would
discard. No shift reaches 64 on a single limb, and no signed overflowing sum,
host floating operation, compiler-specific wide type or imported emulator
implementation is used.

Intel specifies an opposite-sign zero result as negative only when rounding
toward negative infinity; same-sign zeros retain their sign. The helper reads
AC bits 31:30 only when that zero-sign decision is needed. A known bit that
rules out `01` is enough to establish positive zero; otherwise both bits must
be known. Ambiguous control state stops with `undefined_arithmetic_controls`.
Unrelated unknown AC bits never force a needless refusal, and unknown stored
bit values are never treated as evidence.

Exact nonzero arithmetic and same-sign zeros do not depend on rounding
direction. AC flags and their knownness remain unchanged throughout. All
source/control checks precede both destination halves, and successful FP
destinations become defined. Refusal changes only stop diagnostics, retaining
registers, IP and architectural data. The emitted pending-integer-overflow
guard remains intact.

## Explicit limits

Inexact results, subnormal results/operands, infinities, NaNs, noncanonical
extended values, unknown FP operands, floating literals and invalid/reserved
encodings remain unsupported. GPR reset-value knownness is a pre-existing
limitation. Actual floating exception flags/masking, fault delivery, CPU
timing and rounded arithmetic are not implemented by this change. The
existing binary32 ADDR and SUBR subsets are unchanged.

## Verification, October 11, 2026

Seven public ROM-free tests in `tests/test_i960_addrl_native.py` cover:

- 792 binary64 pairs, each in four rounding modes and all eight register
  combinations (25,344 native checks);
- 890 extended80 pairs in four rounding modes and both destination formats
  (7,120 checks), including carry, borrow, exact cancellation, full extended
  precision, exponent gaps 63/64/65, and range limits;
- all stored/known combinations of the two rounding bits checked against
  enumeration of their concrete completions, for zero sums and cancellation;
- aliases, both zero signs, register bounds, zero-plus-normal narrowing,
  special/undefined sources, frame reset and pending-overflow refusal.

The numeric oracle uses Python unbounded `Fraction` addition and independent
rational destination encoding, rather than the runtime's two-limb algorithm.
The shared FP-encoding suite now tests ADDRL reserved bits and FP selectors.
MULRL's six tests are rerun after the source-reader extraction. GCC native
runs use UBSan and strict warnings; Windows Clang 19 checks strict syntax
without disabling warnings. A syntax check is not a Clang execution result;
full-suite and actual CI execution evidence belong to the parent progress
review.

## Private original instruction and static graph

The authenticated original `hotdo` main CPU image has SHA-256
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
Its `ADDRL fp0,fp1,r8` instruction at **0x121C** passes **6,728 isolated
synthetic-state checks** under GCC/UBSan. The private reproduction script is
`build/hotd1/addrl_site_probe.py`; original bytes and generated game C++ remain
private, with generated code written only to a temporary directory.

The bounded two-root walk (`0x5F0`, `0x6B0`, limit 16,384) grows from
**3,248 candidates / 3,247 translations** to **3,311 / 3,311**, with no
unsupported opcode in that discovered graph. This is a **bounded static
translation milestone**, not exhaustive reachable-code coverage. It does not
resolve dynamic targets, value-dependent instruction refusals, authentic
hardware interaction, continuous boot or gameplay. Static translation of an
opcode is not permission to fake its unsupported runtime inputs.

There is no next unsupported static opcode in that walk. Remaining real
blockers include unobserved Sega 315-5649 serial status/RX, rounded arithmetic
and fault/interrupt delivery, then Model 2C geometry/video/audio and gameplay.
No arcade-reference evidence or gameplay speed gain is claimed.

The fresh strict main-CPU probe still completes 1,910 instructions and
refuses the unobserved byte read at `0x01C0001A`, IP `0xA372C`, after 318
mapped writes, 14 CPU-control writes and two documented serial transmissions.
No receive or status value was supplied. This fresh build used GCC 11.4
`-O1 -Wall -Wextra -Werror`: the larger generated program triggered a local
GCC `-O2` internal compiler error during `loop2_invariant`/`move_loop_invariants`.
An additional `-O2 -Werror` attempt also reported array-bounds diagnostics
inside the pre-existing CVTIR helper's FP branch for GPR-destination calls.
The helper's format-dependent bounds guard and generated mode were inspected;
no out-of-bounds runtime access was established. No warning was suppressed
and no source workaround was added. `-O1` is only a private diagnostic build,
not proof that the full original program builds successfully at `-O2`.
The optimizer failure remains a build limitation to investigate separately.

Subjective estimates remain **floating 40% → 40%, CPU 55% → 55%, overall
original HOTD1 10% → 10%**. Gates A/B/C remain open.
