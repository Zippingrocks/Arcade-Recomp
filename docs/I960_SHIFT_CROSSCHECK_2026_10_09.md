# Independent shift cross-check and original-ROM regression

Date: 2026-10-09. **Model 2C is not complete.**

## Reconciled source

The main branch advanced during this verification pass. Its existing
three-target implementation was preserved instead of overwritten by an
older local working copy. The new contribution is
`tests/test_i960_shift_crosscheck.py`, committed as
`01eb97cc2a9003988e707b5d91c45caac02fb973` on top of
`1b38b0df99c15e355db0b7f604d2774c2ca7d20e`.

The underlying functional source was retrieved from the ROM-free CI artifact
for `e8b90f09554a78c13f4c25f9bf9b3d8ebc2553af`. No Sega ROM or generated
original-game executable/source was uploaded to the public repository.

## Actual local validation

The reconciled suite completed successfully:

```text
Ran 96 tests in 37.309s
OK
```

This comprises the latest 94 existing tests and two additional independent
shift tests. The wide-integer reference test exercises four i960 shifts
across 48 source values and 71 counts: 13,632 comparisons per compiler.
Both GCC and Clang passed with UndefinedBehaviorSanitizer enabled. The
second test checks literal counts and register aliasing. This is CPU
functional testing on the Linux host, not a Windows release or original
arcade timing validation.

The primary instruction reference is Intel's original
[80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
printed pp. 11-110/111. Logical shifts must not inherit the host CPU's
modulo-32 count behavior. Arithmetic right shift and division-like right
shift have distinct negative-value rounding behavior.

## Original-ROM regression repeated with the reconciled source

The original uploaded `hotdo` archive matched all 29 chip fingerprints
in this pass. CPU image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

A fresh native build from the reconciled source produced:

| Mode | Executed instructions | Deliberate stop |
| --- | ---: | --- |
| Strict default | 1,904 | IP `0xA375C`, serial write `0x01C00014` |
| Documented TX only | 1,910 | IP `0xA372C`, serial status read `0x01C0001A` |

The latter run recorded channel 2 byte `0xFF` and channel 1 byte `0x01`.
Both probes returned diagnostic exit code 3. Neither enabled artificial
receive/status providers. No additional hardware boundary was crossed.

The same static graph roots (`0x5F0`, `0x6B0`) again yielded 3,051 candidate
addresses, 3,025 native-emission sites, and 26 unsupported sites, without
hitting the discovery cap. These are not a game-completion percentage.

The new address scanner was also rerun against the verified original CPU
image. It reproduced three absolute-store candidates at `0x6B4`, `0x8B88`
and `0x8BA0` for `0x00F80000`, plus three literal-only occurrences. This
confirms the static inventory, not the identity of the physical device.

## Requested work: honest status

The named CPU transfer/shift families are implemented and have functional
tests. Exact memory-bus timing, precise faults/retries and the entire CPU
remain outside that result. The main branch's transfer helper can leave
partial external stores on a later bus fault; it is not an atomic retry
implementation and must not be described as such.

The event-backed Sega 315-5649 serial model remains provisional and needs
actual original-board initial-state, timing and endpoint-response evidence.
The `0x00F80000` device identity is still unresolved. A broader technical
search in this pass did not establish either missing hardware behavior.
Original-board reports in
[MAME issue 11376](https://github.com/mamedev/mame/issues/11376) discuss
serial/MIDI discrepancies, but do not establish HOTD1's 315-5649 endpoint
protocol or identify this board address; they must not be conflated with
proof of those functions.

**The two authentic hardware tasks remain open. All three requested tasks
have not been completed.** See [three-target report](THREE_TARGETS_VALIDATION.md)
and [Model 2C definition of done](MODEL2C_DEFINITION_OF_DONE.md).
