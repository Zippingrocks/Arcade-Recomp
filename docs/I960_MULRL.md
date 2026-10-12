# Intel KB MULRL: exact native long-real multiplication

Implemented: `MULRL` **79Ch** for finite normal values and signed zeros,
with binary64 GPR-pair or canonical extended80 FP-register operands.
The destination can be an even-aligned GPR pair or fp0–fp3. All eight
source/destination register-format combinations are supported within this
exact subset; floating literals remain unsupported.

The primary [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pp. 11-89–11-90, defines multiplication, even GPR-pair alignment
and XOR result sign, including zero. Pages 12-12–12-14 specify that the
destination format determines precision: 53 significand bits for binary64,
64 for extended80. Exact results are independent of rounding mode.
Appendix B selects FP sources with M1/M2; reserved bits 5/6 remain rejected.

## Implementation boundaries

The native helper captures and validates both operands before committing
any result. An explicitly known zero does not hide an undefined second FP
register, a NaN/infinity or a noncanonical source. Source/destination aliases,
including the highest legal GPR pair, preserve captured operands.

Multiplication uses four unsigned 32-by-32 limb products to obtain the full
128-bit product of two normalized 64-bit significands. No host floating
arithmetic, `long double`, compiler-specific 128-bit integer or external
emulator implementation is used. The exactness checks inspect every
discarded bit before narrowing to the destination precision. Exponent
arithmetic and all shifts are bounded; neither word is shifted by 64.

Subnormal/special/noncanonical inputs, underflow/overflow, and products
requiring rounding stop explicitly. AC rounding/normalizing fields,
exception flags and their knownness are preserved on exact success and
diagnostic refusal. This does not implement rounded results, exception
delivery, fault frames or cycle timing. Unknown FP sources remain unknown;
the pre-existing absence of GPR reset-value knownness is not repaired here.

## Evidence

Six ROM-free native tests include:

- 2,192 portable-wide-multiply comparisons against Python unbounded integers;
- 844 binary64 operand pairs in all eight register-format combinations and
  all four rounding-control profiles;
- 708 full-precision extended80 pairs checked at both destination precisions;
- rational result oracles, exponent/precision boundaries, alias combinations,
  signed zeros, mixed formats, unknown sources and atomic refusals.

Native tests use GCC/Clang when available with UBSan. The separate operand
encoding suite now includes MULRL's reserved-bit and FP-index boundaries.

The authenticated original instruction at **0x1200** (`fp0, fp2, r8`)
passed **6,208** isolated native checks with synthetic source/control state
under GCC/UBSan. The reconstructed main-CPU region's SHA-256 is
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
The private verifier is under ignored `build/`; original bytes and generated
game C++ are not published.

At the MULRL checkpoint, the two-root static walk (0x5F0/0x6B0, limit 16,384) discovers **3,242**
candidate instructions and translates **3,241**. It stops at newly exposed
**SQRTR 688h, 0x1204**. This is not a fully translated static program,
exhaustive reachable-code coverage or continuous game execution. Even
translated instructions retain value-dependent unsupported-state stops;
authentic serial RX/status and other hardware boundaries are unchanged.
The subsequent [SQRTR extension](I960_SQRTR.md) records the newer static
frontier; neither checkpoint establishes continuous execution.

Estimated floating progress stays **40%**, CPU **55%**, overall original
HOTD1 **10%**. Gates A/B/C remain open; no cabinet-reference, playable boot,
gameplay or FPS improvement is claimed.

```sh
python -m unittest discover -s tests -p test_i960_mulrl_native.py -v
```
