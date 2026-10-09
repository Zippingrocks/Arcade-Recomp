# HOTD1 three-target implementation and evidence report

Date: 2026-10-09. Starting repository revision:
`6dea173158ff20983a4a518cce277a8ef3b68466`.

## Requested work and actual outcome

| Requested target | Outcome | Not established |
| --- | --- | --- |
| Expand i960 multi-register transfers and shifts | Named instruction families implemented; compiled synthetic and isolated original-opcode checks pass | Complete i960 fault/timing behavior, all game code, remaining unrelated opcodes |
| Finish authentic Sega 315-5649 receive/status | Added explicit event-backed two-channel buffer model, integrated and tested; strict defaults unchanged | Original-board initial state, timing, actual endpoint replies, GPIO/mode/overrun semantics |
| Identify board address `0x00F80000` | Reproducible ROM-wide search found two additional store candidates beyond startup and diagnostic context | Physical device identity, side effects, or justification for ignoring writes |

**Only the named CPU instruction-family implementation is finished within
its stated functional scope. The two authentic hardware tasks remain open.
This report does not declare all three tasks or Sega Model 2C complete.**

## 1. Native i960 instruction additions

`runtime/i960_transfer_shift.hpp` and `arcaderecomp/i960_cpp.py` now lower:

- `LDL/LDT/LDQ` and `STL/STT/STQ`: two-, three-, and four-word transfers.
- `MOVL/MOVT/MOVQ`: aligned register groups and zero-extended literals.
- `SHRI/SHRDI`, plus corrections to existing `SHLO/SHRO` large counts.

The Intel KB programmer manual is the specification: load p. 11-67,
move p. 11-85, shifts pp. 11-110/111, store p. 11-117, literals p. 5-10.
Reference: [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf).

The prior logical-shift emitter incorrectly reduced the count modulo 32.
The new helpers return zero for logical counts at least 32, sign fill for
`SHRI`, and implement `SHRDI` rounding toward zero without host signed
shift assumptions. All count-zero, count-31, count-32, large-count and
negative-value cases avoid undefined C++ behavior.

Memory effective addresses are captured before destination registers can
overwrite the base/index. Loads buffer the result before modifying
registers. Stores snapshot source registers, but a later diagnostic bus
fault can leave earlier writes committed: this is **not** an atomic or
cycle-accurate fault/retry model. Invalid register groups and Intel's
unpredictable overlapping multi-register moves stop explicitly.

### Measured validation

- Seven new CPU unittest methods compile native C++.
- **1,456** synthetic shift reference vectors run with UndefinedBehaviorSanitizer.
- **75 newly supported instruction locations from the actual original ROM**
  passed **450 isolated native checks with synthetic register/memory state**.
  These used private ROM-derived C++ and are not cabinet execution traces.
- Original candidate graph, same roots and same limit:
  **3,051 candidates; 3,025 generate native operations; 26 stop as unsupported**.
  Before this change: 2,950 generated operations and 101 unsupported sites.
- The 75 newly translated sites comprise `LDQ` 9, `STQ` 15, `LDL` 6,
  `STL` 14, `MOVL` 8, `SHRI` 16 and `SHRDI` 7.

The remaining 26 sites include unknown encodings, bit branches,
compare/increment, logical operations and signed arithmetic. These are
**static candidate counts, not a completed-game percentage or proof that
all candidates execute during gameplay**.

## 2. Serial receive/status without a constant-ready shortcut

`runtime/sega3155649_events.hpp` provides a separately selected,
**provisional functional buffer model**, not a finished Sega I/O controller.
`runtime/sega3155649_serial.hpp` exposes it through the existing strict bus.

Each channel tracks an outstanding transmit and a single received byte.
Status low bits are derived from those states; consuming one RX byte
clears that channel's receive-full state. An external provider must supply
an initial idle observation, timestamped transmit completions and actual
receive bytes. Merely advancing time **never** fabricates a completion,
a reply or ready bits. Invalid time order, stale completion tokens, unknown
overflow behavior and empty reads stop instead of silently losing data.

Event-backed operation cannot be mixed with the older arbitrary RX/status
callbacks. It is not enabled in normal strict startup. Five new compiled
tests cover two-channel separation, dynamic status/consumption, time and
token validation, error-bit observations, native polling, and retained
unknown-device boundaries.

Register identities are corroborated by the public
[315-5649 register inventory](https://github.com/mamedev/mame/blob/master/src/mame/sega/315_5649.cpp)
and [Model 2 mapping](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp).
These are research references, not imported device implementations or
proof of original chip timing. The single-byte buffer, consumption and
reject-on-overrun model still needs original-board verification.

**What is missing:** a verified HOTD1/Model 2C capture establishing initial
status, the real TX/RX lifecycle and the actual two channel endpoint
responses. Host test bytes and an assumed baud delay do not supply that
evidence. GPIO, mode registers, calibrated gun inputs and full chip
error/overrun behavior remain outside this implementation.

## 3. New evidence for `0x00F80000`

A reproducible scan of the entire verified 2-MiB original i960 image finds
**six exact aligned occurrences** of this value. Three have immediately
preceding, decode-compatible absolute word-store instructions:

| Candidate instruction address | Stored register | In selected startup graph? |
| --- | --- | --- |
| `0x000006B4` | g6 | Yes |
| `0x00008B88` | r7 | No |
| `0x00008BA0` | g14 | No |

The other three occurrences (`0x000FE250`, `0x0016F2FC`, `0x00173790`)
are reported only as literals, not presumed executable references.

Private static inspection around `0x8B88`/`0x8BA0` finds a diagnostic-looking
loop that disables/restores the IRQ mask, changes other board registers,
calls a check routine, and prints GOOD/BAD results. This **suggests a
service/diagnostic context**; it does not prove this path has run, what g14
contains at every entry, or what physical circuit responds. The nearby
r7 assignment is 2 before the first store.

This matters because the address should not be described solely as a
single irrelevant startup write. A public legacy emulator explicitly
ignores a similarly addressed boot write to suppress logging:
[libretro/mame2010 model2.c at dff8aadd](https://github.com/libretro/mame2010-libretro/blob/dff8aadd1c3f38215af3955746d6e19abe0ddcea/src/mame/drivers/model2.c).
That is a **software workaround**, not identification of the device and
not evidence that ignoring all accesses is arcade-faithful.

The new metadata-only scanner `arcaderecomp/mmio_refs.py` distinguishes
absolute accesses, address construction, displacement-only occurrences
and uninterpreted literals. Root-graph membership remains a static label.
Four synthetic tests check classification, baseline hash validation,
invalid roots and truncated trailing data. The original result is saved
in `docs/reports/hotdo_f80000_address_audit.json`; it contains no ROM bytes.

**No device name, watchdog interpretation, no-op handler, invented
readback or write acknowledgement was added. The strict fault remains.**

## Actual original-ROM regression

Input: all **29** original `hotdo` chips match expected size, CRC32 and SHA-1.
Reconstructed CPU image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

The final source passes **94** synthetic/compiled automated tests locally.
Its actual original-ROM strict probe still gives:

| Mode | Executed native instructions | Boundary |
| --- | ---: | --- |
| Strict default | 1,904 | IP `0xA375C`, unknown TX write `0x01C00014` |
| Documented TX enabled only | 1,910 | IP `0xA372C`, unavailable status read `0x01C0001A` |

The TX-enabled run records TX2=`0xFF` and TX1=`0x01`. No observed-event
backend, invented status, gun data or fake serial fixture was used in these
regression runs. They remain diagnostics with incomplete CPU-control timing,
not original-cabinet parity.

## Reproduction

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 --output build/hotd1/hotd1_i960.cpp
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000 --serial-tx
python -m arcaderecomp.mmio_refs --image build/hotd1/maincpu.bin --address 0x00f80000 --root 0x5f0 --root 0x6b0 --expected-sha256 da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75
```

The strict probe's exit code 3 denotes the deliberate device boundary, not
successful arcade startup. Original images, emitted game-specific C++ and
private binaries must stay outside the public repository.

## Evidence needed to finish the two hardware targets

A useful original-board recording must identify the exact Model 2C PCB
revision and ROM hashes, and contain time-related CPU MMIO accesses plus
the corresponding serial TX/RX/status events. For `0x00F80000`, a schematic,
address-decoder tracing or instrumented original-board observation around
both startup and the diagnostic accesses is needed to establish its actual
effect. A screenshot or emulator that ignores the address is insufficient.

Until those gaps are resolved, issues #4 and #6 remain open and the
promised **Sega Model 2C completion declaration is not warranted**.
