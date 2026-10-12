# Intel KB extended-real sign copying

Implemented subset: native AOT `CPYSRE` (6E2h) and `CPYRSRE` (6E3h)
for defined canonical normal extended80 register values. Synthetic-tested,
without original-ROM instruction-site or arcade-reference verification.

The [Intel 80960KB manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pp. 11-48, 12-15 and 12-20, defines magnitude from source 1 and
sign from source 2. CPYRSRE reverses the source 2 sign. The runtime copies
bits without host floating-point arithmetic or format conversion.

Each operand can use fp0–fp3 or an extended-real GPR triple starting at a
multiple-of-four register. At least one operand must use an FP register
in this supported subset. Floating literals and wholly GPR operations
remain untranslated. GPR source padding above bit 79 is ignored; GPR
destination padding above bit 79 is zeroed. Both source values are
captured before destination mutation, so source/destination aliases and
reverse-copying a value's own sign work.

Both source values must be defined and canonical normal extended80:
exponent 1–32766 with the explicit leading significand bit set. Unknown
FP sources stop, preserving the old destination and its knowledge marker.
Zero, subnormal, unnormal, infinity and NaN cases remain unsupported.
The instruction entry's reserved-encoding fault text on p. 11-48 and
the nonarithmetic/no-FP-fault discussion on p. 12-20 differ for denormals.
This subset deliberately avoids that unresolved edge rather than claiming
full hardware behavior. Rejections are diagnostic stops, not Intel fault
entry. Exact success preserves modeled condition and process controls.

ROM-free GCC/Clang UBSan tests (when compilers are available) cover both
instructions, all seven supported GPR/FP mode combinations, 300 normal
payloads, both signs for both sources, eight condition-code values,
padding, aliases, unknown source markers, invalid encodings/alignment and
nonnormal refusal. They do not establish guest program reachability or
physical timing.

```sh
python -m unittest discover -s tests -p test_i960_copy_sign_native.py -v
```

CPU floating-point remains estimated at 40%, native CPU 55%, Model 2C
20%, and overall original HOTD1 10%. Original 315-5649 status/RX,
FP rounding/faults, interrupts, geometry, display, audio and gameplay
remain uncompleted work.
