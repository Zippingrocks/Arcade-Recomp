# ArcadeRecomp

**Independent ahead-of-time recompilation research for classic arcade systems.**

## Project 001 — The House of the Dead, original arcade revision

The first target is Sega's **Model 2C original arcade game**, catalogued as
**`hotdo`** (1997), not the Saturn/Windows conversion, modern remake or
later Revision A. Preserve original arcade behavior before enhancements.

| Revision | MAME ID | Role |
| --- | --- | --- |
| Original release | `hotdo` | Primary |
| Revision A | `hotd` | Separate secondary target |
| Prototype | `hotdp` | Historical target after retail fidelity |

Original program chips are `epr-19696.15` (CRC32 `03da5623`, SHA-1
`be0bd34a9216375c7204445f084f6c74c4d3b0c8`) and `epr-19697.16` (CRC32
`a9722d87`, SHA-1 `0b14f9a81272f79a5b294bc024711042c5fb2637`). Revision A
uses the separately named `epr-19696a.15` and `epr-19697a.16`. The manifest
checks all 29 original chips by size, CRC32 and SHA-1. Archive names and
MAME parent/clone relationships are not proof of release identity.

## Current status — Model 2C NOT COMPLETE

**Latest local validation: 137 tests passed.** The latest CPU pass adds
NOT, ANDNOT, CHKBIT, BBC/BBS, all eight TEST conditions and CMPINCI/CMPINCO.
It executes 54,978 synthetic case rows under each of GCC and Clang with
UndefinedBehaviorSanitizer. The 17 newly supported original-ROM locations
also pass 2,912 isolated synthetic-state checks per compiler.
See the [implementation and validation report](docs/HOTDO_BIT_COMPARE_NATIVE.md).

The unchanged two-root original candidate graph contains **3,051 locations**:
**3,042 emit native operations**, **9 deliberately stop**. Previously those
counts were 3,025 and 26. These are static candidates, **not a game-completion
percentage**, all discovered gameplay paths or a completed CPU.

Earlier support includes local CALL/CALLX/RET frames, BAL/BALX/BX leaf
branches, selected synchronous CPU-control operations, LDL/LDT/LDQ,
STL/STT/STQ, MOVL/MOVT/MOVQ, and SHRI/SHRDI with large-count logical shifts.
Precise exceptions, retry, tracing and timing remain incomplete. A later
fault in a multiword store can leave earlier writes committed; diagnostic
stops must not be resumed as if the operation were atomic.

### Authentic startup boundary remains unchanged

The actual original ROM executes **1,904** successful native steps in
strict default mode before stopping at the first serial TX write. With
only documented TX enabled, it executes **1,910** steps: TX2=FF, TX1=01,
then stops at unavailable serial status `0x01C0001A`, IP `0x000A372C`.
Both return diagnostic exit 3, not a passed boot. No fabricated receive
bytes or ready signals are used in these regression runs.

**There is no playable game, working graphics/audio platform or verified
original-cabinet interrupt delivery yet.** CPU faults/timing, authentic
serial responses, interrupts, MB86235/TGPx4 geometry, rendering, sound and
complete gameplay validation remain open.

### Hardware and research boundaries

The optional [event-backed serial model](runtime/sega3155649_events.hpp)
requires an explicit initial observation and externally supplied TX/RX
events. Time alone never creates replies; strict startup does not enable it.
[Upload tests](docs/HOTD1_SERIAL_UPLOAD_AND_MEMORY_TEST.md),
[variable-input experiments](docs/HOTDO_VARIABLE_SERIAL_SCHEDULE.md), and
the [gun-board/FPGA hypothesis](docs/HOTDO_UPLOAD_RECORDS_AND_GUN_BOARD.md)
provide host-side evidence, **not authentic receiver responses or proven
FPGA configuration decoding**. Issue #4 remains open.

The [address audit](docs/reports/hotdo_f80000_address_audit.json) identifies
store candidates at `0x000006B4`, `0x00008B88` and `0x00008BA0`. Additional
memory-test context does not establish the circuit at `0x00F80000`.
No guessed watchdog or no-op mapping was added. Issue #6 remains open.

A historical experiment with explicitly **fictional serial inputs** reached
91,118 original-program steps, an opt-in IAC 0x93 transition and the unknown
board write. It is not authentic arcade boot evidence. Isolated instruction
probes and the optional partial IRQ register model do not establish cabinet
interrupt delivery either.

## Reproduce with a private original ROM

Requirements: Python 3.10+, a C++17 compiler, and system libarchive for
`.7z` input. ZIP input uses Python's standard library. The new native tests
use every installed GCC/Clang compiler. The original-site verifier requires
both by default, or explicit repeated `--cxx` selections.

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python tools/experimental/hotdo_bit_compare_probe.py --image build/hotd1/maincpu.bin --output build/hotd1/bit-compare.json
```

The [latest report](docs/HOTDO_BIT_COMPARE_NATIVE.md) includes strict-probe
commands. Exit 3 denotes an unimplemented device boundary; exit 4 denotes
unsupported CPU behavior. Generated ROM images, game-specific C++ and
native game-derived binaries stay private.

## Non-negotiable goals

Develop the recompiler independently; no Daytona implementation is copied.
Publish original tools, synthetic tests and factual metadata, never Sega
ROMs or assets. Unknown hardware is not replaced by fictional success.

The binding [Model 2C definition of done](docs/MODEL2C_DEFINITION_OF_DONE.md)
separates CPU support, integrated platform operation and full original-game
validation. The explicit **“SEGA MODEL 2C RECOMPILATION SUCCESSFULLY
COMPLETED!”** announcement is reserved for the final verified gate, not a
title screen or test count. HOTD1 validation does not prove every other
Model 2C title works.

## Earlier evidence

- [Three-target transfer/shift and hardware report](docs/THREE_TARGETS_VALIDATION.md).
- [Original audit](docs/HOTD1_ORIGINAL_AUDIT.md), [strict trace](docs/HOTD1_ORIGINAL_NATIVE_TRACE.md), [earlier CPU inventory](docs/HOTD1_WIDENED_I960_COVERAGE.md).
- [IAC experiment](docs/HOTD1_IAC_REINITIALIZATION_STAGE2.md), [ICR probe](docs/HOTD1_INTEL_ICR_STAGE2.md), [frames](docs/I960_FRAMES.md), [leaf branches](docs/I960_LEAF_BRANCHES.md).
- [Serial research](docs/SEGA_IO3155649.md), [IRQ research](docs/MODEL2C_INTERRUPT_REGISTER_RESEARCH.md), [SYNLD](docs/I960_SYNLD_PIN_ROUTING.md).
- [Provenance](docs/PROVENANCE.md), [hardware notes](docs/MODEL2C_HARDWARE.md), [roadmap](docs/ROADMAP.md).
- External inventories: [MAME Model 2 layouts](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp), [Arcade Museum original set](https://www.arcade-museum.com/tech-center/machine/hotdo), [Sega history](https://www.sega.jp/history/arcade/).
