# ArcadeRecomp

**Independent ahead-of-time recompilation research for classic arcade systems.**

## Project 001 — The House of the Dead, original arcade revision

The authoritative first target is Sega's **Model 2C original arcade game**, catalogued as **`hotdo`** (1997), not the Saturn/Windows conversion, modern remake, or later Revision A.

| Revision | MAME ID | Role |
| --- | --- | --- |
| Original release | `hotdo` | Primary |
| Revision A | `hotd` | Separate secondary target |
| Prototype | `hotdp` | Historical target after retail fidelity |

Distinctive original program chips:

- `epr-19696.15`: CRC32 `03da5623`, SHA-1 `be0bd34a9216375c7204445f084f6c74c4d3b0c8`.
- `epr-19697.16`: CRC32 `a9722d87`, SHA-1 `0b14f9a81272f79a5b294bc024711042c5fb2637`.

Revision A instead uses `epr-19696a.15` and `epr-19697a.16`. Archive names do not prove identity. The manifests check all 29 original chips by size, CRC32 and SHA-1. MAME parent/clone packaging is not release chronology.

## Current status — Model 2C NOT COMPLETE

**94 tests pass locally and in [GitHub Actions](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37918124810) at source commit `e8b90f09554a78c13f4c25f9bf9b3d8ebc2553af`.**

The latest work addressed three named targets:

| Target | Delivered | Still open |
| --- | --- | --- |
| i960 multi-register transfers and shifts | Named families implemented and tested, including large-count shift fixes | Full CPU timing/fault behavior and unrelated opcodes |
| Sega 315-5649 receive/status | Event-backed two-channel buffers and explicit completion/receive input | Authentic initial state, timing, endpoint responses and full chip behavior |
| `0x00F80000` | ROM-wide audit finds startup plus two further store candidates | Actual device identity and physical side effects |

**The CPU instruction-family work is complete within its stated functional scope. The two authentic hardware tasks are not finished.** See the [three-target evidence report](docs/THREE_TARGETS_VALIDATION.md).

### Original-ROM execution and its boundaries

The actual original ROM still executes **1,904** native instruction steps in default strict mode, stopping at the first serial TX write. Enabling documented TX only permits **1,910** steps: TX2=`0xFF`, TX1=`0x01`, then a deliberate halt at the unavailable serial-status read `0x01C0001A`, instruction `0x000A372C`. No invented receive bytes or ready signals are used in those regression runs.

A separate, explicitly **fictional serial-input** experiment previously executed 91,118 original-program steps, applied an opt-in i960 IAC `0x93` PRCB transition, entered `0x000006B0`, and stopped at the unknown board write `0x00F80000`. It is not arcade-fidelity boot evidence. Isolated original IAC and ICR instruction probes are also distinct from continuous startup.

**There is no playable game, working graphics/audio platform or verified original-cabinet interrupt delivery yet.** CPU-control timing, true serial responses, interrupts, MB86235/TGPx4 geometry, rendering, audio and gameplay remain incomplete.

### Native CPU instruction coverage

The translator supports a growing functional subset, including local CALL/CALLX/RET frames, BAL/BALX/BX leaf branches, synchronous CPU-control operations, condition masks, and now:

- `LDL/LDT/LDQ`, `STL/STT/STQ`, and `MOVL/MOVT/MOVQ`.
- `SHRI/SHRDI`, plus correct large-count handling for `SHLO/SHRO`.

The unchanged two-root original candidate graph contains **3,051 locations**: **3,025 emit native operations**, **26 deliberately stop**. Before the new transfer/shift work those counts were 2,950 and 101. The 75 newly supported original locations passed 450 isolated native tests using synthetic CPU/memory state; 1,456 synthetic shift vectors also pass UndefinedBehaviorSanitizer.

These are **static candidate and isolated-test figures**, not a completed-game percentage or proof of all gameplay paths. Precise CPU exception/retry behavior remains incomplete.

### Serial and board research

The optional [event-backed serial model](runtime/sega3155649_events.hpp) requires an explicit initial observation and externally supplied TX completion/RX events. Ready bits follow buffer state; time alone never creates replies. Unknown overflow semantics, empty reads and unverified device registers stop safely. Normal strict startup does not enable this backend.

The [address audit](docs/reports/hotdo_f80000_address_audit.json) finds store candidates at `0x000006B4`, `0x00008B88` and `0x00008BA0`. The latter two sit in diagnostic-looking code but are not reached by the selected startup graph. This adds evidence beyond a lone startup write; it **does not identify the circuit**. No watchdog guess or no-op handler was added.

The existing [partial IRQ registers](runtime/model2c_irq_registers.hpp) remain opt-in, with synthetic event tests only. Intel ICR pin-role decoding and synchronous readback are not full interrupt delivery.

## Reproduce with a private original ROM

Requirements: Python 3.10+, a C++17 compiler for native tests, and system libarchive for direct `.7z` input. ZIP input uses the Python standard library. A parent archive is unnecessary when all 29 original chips are present.

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 --output build/hotd1/hotd1_i960.cpp
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000 --serial-tx
python -m arcaderecomp.mmio_refs --image build/hotd1/maincpu.bin --address 0x00f80000 --root 0x5f0 --root 0x6b0 --expected-sha256 da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75
```

Strict probe exit 3 means an unimplemented device boundary; exit 4 means unsupported CPU behavior. Neither is a passed arcade boot. Generated ROM images, game-specific C++ and native game-derived binaries stay private.

## Non-negotiable goals

Preserve original arcade behavior before optional enhancements. Develop the recompiler independently; no Daytona implementation is copied. Publish original tools, synthetic tests and factual metadata, never Sega's game ROMs or assets. Unknown device behavior is not replaced by fictional success.

The [binding Model 2C definition of done](docs/MODEL2C_DEFINITION_OF_DONE.md) separates CPU support, integrated platform operation and full original-game validation. The explicit **“SEGA MODEL 2C RECOMPILATION SUCCESSFULLY COMPLETED!”** announcement is reserved for the final verified gate, not a title screen or test count. HOTD1 validation also does not prove every other Model 2C title works.

## Evidence and earlier milestones

- [Latest three-target implementation and evidence report](docs/THREE_TARGETS_VALIDATION.md).
- [Original ROM audit](docs/HOTD1_ORIGINAL_AUDIT.md), [strict native trace](docs/HOTD1_ORIGINAL_NATIVE_TRACE.md), and [earlier widened static inventory](docs/HOTD1_WIDENED_I960_COVERAGE.md).
- [IAC reinitialization experiment](docs/HOTD1_IAC_REINITIALIZATION_STAGE2.md), [isolated ICR test](docs/HOTD1_INTEL_ICR_STAGE2.md), [frame research](docs/I960_FRAMES.md), and [leaf branches](docs/I960_LEAF_BRANCHES.md).
- [Sega serial research](docs/SEGA_IO3155649.md), [IRQ research](docs/MODEL2C_INTERRUPT_REGISTER_RESEARCH.md), [SYNLD and pin roles](docs/I960_SYNLD_PIN_ROUTING.md).
- [Provenance](docs/PROVENANCE.md), [hardware notes](docs/MODEL2C_HARDWARE.md), and [roadmap](docs/ROADMAP.md).
- External factual references: [MAME Model 2 ROM/layout inventory](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp), [Arcade Museum original set](https://www.arcade-museum.com/tech-center/machine/hotdo), [Sega arcade history](https://www.sega.jp/history/arcade/).
