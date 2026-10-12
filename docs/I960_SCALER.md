# Intel 80960KB SCALER: exact native subset

Status: implemented and synthetic-tested; no original-ROM instruction-site
or independent arcade-reference validation yet.

Primary reference: [Intel 80960KB Programmer's Reference Manual, March
1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
Chapter 11 pp. 11-105–11-106. SCALER opcode is **677h**; SCALERL is
the distinct **676h** opcode and remains unsupported. Operand order is
signed integer `src1`, real `src2`, real destination. The operation is
`dst = src2 * 2^src1`.

The independent decoder and AOT emitter now recognize SCALER. Native
execution supports an integer GPR or 5-bit integer literal for `src1`,
and finite normal binary32 values in GPRs for `src2` and destination.
When the mathematical result is also normal binary32, scaling is exact:
the sign and all fraction bits are retained. No host float arithmetic,
rounding controls, or library `pow`/`ldexp` operation is used by the runtime.
Signed counts, including INT_MIN and INT_MAX, are decoded and added in
wide integer arithmetic without signed overflow or unbounded shifts.
Operand values are captured before destination writes, preserving aliases.

Zero, subnormal, infinity and NaN operands, results outside the normal
binary32 range, floating-register/literal modes, and SCALERL deliberately
stop. Even an exactly representable subnormal result remains unsupported
because the relevant Intel normalization and underflow behavior is not
implemented. These stops are diagnostic limitations, not architected
fault delivery. Unsupported execution leaves destination and IP unchanged.
Exact success preserves condition codes and other modeled control state.

ROM-free tests exercise all 254 normal source exponent fields, both signs,
three fraction patterns and seven signed scale counts: **10,668 vectors**.
Expected results use independent Python rational multiplication followed by
IEEE binary32 packing, rather than the runtime's exponent-edit algorithm.
Additional tests cover integer literals, source/destination and
count/destination aliases, unsupported encodings, special values, extreme
counts, failed direct calls, and condition-code preservation. Native test
compilation uses GCC and Clang when available, with UndefinedBehaviorSanitizer.

```sh
python -m unittest discover -s tests -p test_i960_scaler_native.py -v
```

This extends real native CPU execution coverage but does not establish
original HOTD1 use of SCALER or uninterrupted arcade startup. CPU floating
progress remains estimated at 40%, native CPU 55%, Model 2C 20%, and
overall original HOTD1 10%. Authentic 315-5649 RX/status, CPU FP faults and
rounding, interrupts, geometry, display, audio, and gameplay remain open.
