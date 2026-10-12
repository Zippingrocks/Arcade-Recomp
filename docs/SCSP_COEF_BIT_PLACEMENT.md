# SCSP COEF bus-bit placement correction

Status (2026-10-12): COEF's 13-bit field is now placed in bus bits 15:3,
matching Sega table 4.5. The earlier low-13-bit interpretation was wrong and
has been corrected rather than relaxed around an authentic failing byte.

The SCSP User's Manual labels each word `COEF[12:0] | 0 | 0 | 0`: coefficient
bit 12 is bus bit 15 and coefficient bit 0 is bus bit 3. Consequently the
register mask is `0xfff8`, not `0x1fff`. On the MC68000 big-endian bus:

- every high-byte value is valid and establishes bus bits 15:8;
- a low-byte value is valid only when bits 2:0 are zero;
- aligned word writes require `(value & 7) == 0`; and
- value-bearing low-byte or word reads still fail until the three reserved low
  bits have a defined hardware readback, while CLR discarded reads remain safe.

Tests exhaust all 65,536 word values, all 256 values on both byte lanes, all
64 registers, knownness, bounds and the original longword clear sequence.
The complete suite passes 762 tests in 209.088 seconds.

The authenticated original upload's first high byte is known `0x7f`; it is
valid under the manual placement. The matching low byte is accepted, yielding
two upload writes before execution reaches:

```text
PC 0x00600296: JMP (A1)
A1 = 0x006002a2 (known)
completed instructions: 308040 / 308042 / 308043 by signature route
```

The next blocker is a known-target runtime-indirect jump whose target is not
yet in the static AOT graph. Correct support must preserve fixed generated
dispatch and prove/enroll reachable targets; it must not turn the runtime into
an interpreter or accept arbitrary guest addresses. DSP execution, timing and
audio remain absent, so estimates and completion gates do not change.
