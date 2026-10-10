# Original i960 ADDI/SUBI with explicit overflow handoff

Date: 2026-10-10. Base: `7c13a0e94f3955114ac06fea38daf58dcbf52830`.

**Model 2C is NOT complete. The authentic serial startup boundary is unchanged.**
This pass implements two missing CPU instruction families at three original-game
sites. It does not invent serial replies, assign semantics to `0x00F80000`, or
claim a working guest fault handler.

## Specification and the important post-result distinction

Primary source: Intel, *80960KB Programmer's Reference Manual*, 1988,
order 270567-001. [Manufacturer manual scan](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf).
Printed pages 3-7 and 3-9/10 describe arithmetic controls; 9-16 describes integer
overflow faults; 11-7 and 11-120 define ADDI/SUBI. The machine-readable text was
checked. The PDF screenshot endpoint was unavailable during this pass; no visual
inspection of that scan is claimed.

ADDI computes src2 + src1; SUBI computes src2 - src1. The comparison condition
code is not modified. AC bit 12 controls integer-overflow masking. Masked
overflow stores the low 32 result bits and sets the sticky AC bit 8 flag.
Non-overflow does not clear that flag. An unmasked overflow stores the result
before signalling a fault and does not set the overflow flag. Intel's arithmetic
fault reference specifies the following instruction as the saved return point:
a handler must not reexecute an instruction that already overwrote its operands.

The runtime is sequential and does not implement scoreboarding, NIF-dependent
imprecise fault interactions, instruction timing, or multiple concurrent faults.
The recorded next-IP value is an explicit sequential-model handoff, not a claim
that every unmodeled concurrent silicon state has been reproduced.

## Implementation

`runtime/i960_integer_arithmetic.hpp` performs result and overflow detection
using unsigned host operations. Expected results in tests are calculated using
Python's unbounded signed integers, not that same bitwise detection formula.
The AOT emitter lowers decoded register/literal ADDI and SUBI forms directly to
these helpers. No instruction decoding is added to native execution.

The CPU tracks only the two relevant arithmetic-control bits and whether each
is known. They are not silently taken as zero after reset or reinitialization:
Intel leaves AC undefined. A normal, non-overflowing add/subtract can execute
without a known mask because its outcome does not depend on the mask.

| Case | Result and flag handling | Progress |
| --- | --- | --- |
| No overflow | Store result; preserve overflow flag and compare condition | Advance normally |
| Overflow, known mask set | Store result; set sticky overflow flag; preserve compare condition | Advance normally |
| Overflow, known mask clear | Store result; preserve overflow flag; record faulting and next IP | Stop with pending overflow handoff |
| Overflow, mask unknown | Do not change result or flags | Stop before mutation with unknown-control diagnostic |

The generated `step()` refuses further instruction execution while that overflow
handoff is pending. Retrying `step()`, changing its IP, or supplying a new mask
cannot accidentally execute the instruction twice or bypass the pending fault.
This is distinct from the unknown-mask diagnostic, which has not committed the
result and may be retried after the caller establishes the missing state.

`establish_integer_controls()` is a host-side state import/fixture helper,
**not** guest MODAC, a reset default, or automatic fault recovery. The pending
structure is diagnostic data, not an architected memory fault record. There is
no implemented fault-table dispatch, supervisor frame construction, guest
handler execution or return from the new fault. Reset/reinitialization clears
pending diagnostics and invalidates knowledge of these arithmetic controls;
an invalid reinitialization request does not clear them.

## Original-game sites and static result

The original verified image contains three previously unsupported sites in the
same two-root graph:

| Site | Instruction family |
| --- | --- |
| `0x00001034` | SUBI, destination aliases src2 |
| `0x0000103C` | ADDI, destination aliases src2 |
| `0x00001060` | ADDI with literal 1, destination aliases src2 |

The graph remains **3,051 static candidates**. Native-emitting sites increase
from **3,042 to 3,045**, and unsupported sites fall from **nine to six**. The
remaining sites are `0x5C0`, `0xBFC`, `0x11CC`, `0x1384`, `0x13D80` and `0x334D8`.
This is not a full-game coverage or completion percentage; other dynamic targets
and hardware dependencies remain outside this fixed discovered graph.

## Validation actually performed

The downloaded source ZIP matched its advertised SHA-256
`bd211b0a80f1053278cee080ed0f7d5e16df990ae48a2cf8e3d938e931361977`.
The untouched source passed **346 tests** locally.

Eleven new arithmetic tests run compiled synthetic instructions under **GCC and
Clang**, with warnings as errors and UndefinedBehaviorSanitizer. The broad
independent oracle executes **36,864 comparisons per compiler**, covering both
instructions, edge and seeded input pairs, known/unknown mask and sticky flag
states, and defined/undefined comparison state. Other checks cover aliases,
literal operands, sticky flags, mutation-before-trap, repeat execution blocking,
reset/IAC invalidation and rejected operand encodings.

Five additional audit tests check private-image identity, complete metadata,
input/output hard-link protection, known case counts and the compiled harness
itself. A deliberately wrong expected arithmetic value makes that harness fail.
The complete final local suite passed **362 tests**.

`arcaderecomp.signed_arithmetic_audit` validates the exact original image hash and
instruction operand forms, privately compiles the original AOT graph and executes
the three original instructions in isolation. It tests **1,672 input vectors**
across 32 control/condition states: **53,504 comparisons per compiler**. GCC and
Clang both pass with UBSan and produce identical metadata. Destination aliasing,
untouched registers, result, flags, IP and pending-fault behavior are checked.

These use **original instructions with synthetic CPU state**, not captured
arcade execution. The generated game C++ and native test executables remain in
private temporary directories and are removed. No original opcode words, ROM
bytes or game-derived binaries are committed.

### Fresh original-game regression

All **29 original hotdo chips** match size, CRC32 and SHA-1. The rebuilt CPU image
SHA-256 remains `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

| Run | Successful native instructions | Deliberate stop |
| --- | ---: | --- |
| Default strict | 1,904 | Disabled TX write, IP `0xA375C` |
| Documented TX only | 1,910 | Missing serial status `0x01C0001A`, IP `0xA372C` |

Both return diagnostic exit 3. The second records TX2=FF and TX1=01. Neither
uses synthetic RX/status input. The arithmetic tests do not move those hardware
boundaries and are not evidence of a newly completed authentic boot.

## Hardware research outcome and reproduction

This pass revisited serial-reply and `0x00F80000` leads. No new matching raw
Model 2C receive capture or independently supported register definition was
obtained. The earlier Model 2B TX observations and tentative RAM-write-protection
comment remain qualified leads, not a basis for manufacturing hardware behavior.
The productive implemented change is the original-game CPU arithmetic above;
the existing serial/device runtime was not altered.

```sh
python -m unittest discover -s tests -p test_i960_integer_arithmetic.py -v
python -m unittest discover -s tests -p test_signed_arithmetic_audit.py -v
python -m unittest discover -s tests -v
# Existing private, authenticated maincpu image; no network or ROM fetch:
python -m arcaderecomp.signed_arithmetic_audit \
  --image build/hotd1/maincpu.bin \
  --output build/hotd1/signed-arithmetic.json
```

[Measured original-opcode audit](reports/hotdo_signed_arithmetic.json).
[Binding Model 2C completion gates](MODEL2C_DEFINITION_OF_DONE.md).
Authentic serial replies, FPGA acceptance/circuit behavior, `0x00F80000`, full
CPU exceptions, graphics and sound remain unresolved. **No completion gate is
being declared passed.**
