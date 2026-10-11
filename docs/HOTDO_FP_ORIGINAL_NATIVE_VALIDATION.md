# Original HOTD1 native floating-point validation

**Status: original ROM instruction bytes verified with synthetic CPU inputs.**
This does NOT establish continuous arcade boot, physical Sega Model 2C I/O
behavior, or complete Intel 80960KB floating-point fault and rounding support.

## Authenticated original

The private original hotdo main-CPU region is 2,097,152 bytes with SHA-256
da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75.

No commercial ROM bytes, ROM-derived translated C++ or original game executable
appear in this repository or the metadata result files.

## Authentic instruction-site native execution

The previously implemented private three-step checker was run against the
authenticated original image with GCC and Clang and UndefinedBehaviorSanitizer.
At each of four original sites, it uses the real LOGBNR, ADDR, CVTZRI instruction
bytes and a synthetic CPU register state. All 2,739 test cases per site passed,
for **10,956 native executions per compiler**:

| Entry address | Original native sequence |
| --- | --- |
| 0x00000BFC | LOGBNR, ADDR, CVTZRI |
| 0x00000C24 | LOGBNR, ADDR, CVTZRI |
| 0x00000C4C | LOGBNR, ADDR, CVTZRI |
| 0x00000C7C | LOGBNR, ADDR, CVTZRI |

The new opt-in checker at tools/experimental/hotdo_fp_arithmetic_probe.py
authenticates the same original CPU image and verifies three other isolated
original-ROM instructions under GCC and Clang with UBSan:

| Address | Original instruction | Status |
| --- | --- | --- |
| 0x000011F8 | DIVR r4,g4,g6 | Passed |
| 0x00001390 | MULR g5,g13,g4 | Passed |
| 0x00013D88 | MULR g5,r7,g5 | Passed |

For each original instruction, 2,039 synthetic pairs (edge cases, exact powers
of two, random finite values and exceptions) are checked against independent
Python Fraction rational arithmetic, verifying normal exact binary32 outcomes,
signed zero, operand direction and overlapping destination registers.
**6,117 native arithmetic executions passed per compiler.** Inexact results,
invalid values, subnormal operands, over/underflow and divisor zero must
stop without modifying CPU state. That is a controlled incompleteness, not
an implemented architected floating-point fault.

Both private checkers require original input SHA-256, validate opcode and
register fields, keep generated original C++ in temporary directories, and
export only JSON metadata. New ROM-free unit tests check wrong hashes and sizes,
wrong original instruction identity, oracle cases and prevention of hardlink
or symlink report overwrites.

## Unmodified strict startup still blocked

An additional private original-ROM native startup check, with only documented
serial TX enabled, executed **1,910** original instructions, transmitted TX2=FF
and TX1=01, and stopped on a required serial-status read at 0x01C0001A.
The strict bus correctly refused to invent readiness or receive bytes.

## Reproduce privately

Supply your own reconstructed authentic original 2-MiB main-CPU image, then:

    python tools/experimental/hotdo_fp_sequence_probe.py --image /private/maincpu.bin --output /private/triplets.json --cxx g++ --cxx clang++
    python tools/experimental/hotdo_fp_arithmetic_probe.py --image /private/maincpu.bin --output /private/arithmetic.json --cxx g++ --cxx clang++
    python -m unittest discover -s tests -p test_hotdo_fp_arithmetic_probe.py -v

The synthetic-state original-site checks do not prove that the game reaches
these instructions after a real uninterrupted startup. Authentic serial RX,
status timing, CPU exception delivery, interrupts, MB86235 geometry, display
and sound all remain separate uncompleted Model 2C implementation requirements.
