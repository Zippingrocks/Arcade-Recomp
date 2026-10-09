# HOTD1 second-stage i960KB interrupt-control register (ICR)

**Status: SYNTHETIC-TESTED + ISOLATED ORIGINAL-ROM TESTED. Hardware fidelity incomplete.**  
**Sega Model 2C is NOT complete.**

## Independent evidence

The public [Intel 80960KB Programmer's Reference Manual (March 1988), Chapter 8, page 8-11](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf) specifies that the processor's internal **interrupt-control register (ICR)** is mapped to `0xFF000004..0xFF000007`, accessible through `SYNMOV` and `SYNLD`. It identifies **`0xFF000000`** as the ICR's value after processor initialization.

The same Intel manual (Chapter 11, page 11-126) defines **`SYNMOV`** as a one-word *synchronous* memory-to-memory operation. A successfully completed transaction sets `AC.cc=010`. Ordinary asynchronous peripheral writes must **not** be treated as sufficient evidence that a synchronous transaction has completed.

## Original HOTD1 program observations

Verified original `hotdo` ROM, static i960 disassembly:

| ROM address | Original instruction / program datum |
| --- | --- |
| `0x000006B0` | `mov 2,g6` |
| `0x000006B4` | `st g6,0x00F80000` — **unknown Model 2C hardware address** |
| `0x000006C4` | `lda 0xFF000004,g4` — internal Intel KB ICR |
| `0x000006CC` | `lda 0x000006A8,g5` — original program data |
| `0x000006D4` | `synmov g4,g5` — synchronous word write to ICR |
| `0x000006A8` | **`0x0F0E0D0C`** — the ICR value in the original ROM |
| `0x000006D8` | Next original instruction is a procedure call |

As a 32-bit ICR value, the four vector fields are `INT0=0x0C`, `INT1=0x0D`, `INT2=0x0E`, and `INT3=0x0F` (least- to most-significant byte). This identifies the intended assignment values, **not** proof that original interrupt signals, priorities, or service routines already work in ArcadeRecomp.

### Crucial Model 2C address boundary

`0x00F80000` is a **separate** address from the Intel internal ICR `0xFF000004`. The current public MAME Sega Model 2 driver does **not** assign a handler to `0x00F80000`. Its physical meaning (if any) has not been independently established. We deliberately retain a strict fault at `0x00F80000`; calling it a watchdog or discarding the write would be speculation.

Public technical map reference: https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp

## Implemented natively

- `runtime/i960_frame_runtime.hpp`: models `interrupt_control_register`, initialized to the Intel KB-documented `0xFF000000` during frame initialization/reinitialization.
- `runtime/i960_sync_runtime.hpp`: `sync_move_word` recognizes only the CPU's **internal** word-aligned `0xFF000004` ICR destination, reads the mapped source word, commits the ICR value and sets condition code `010`. It refuses an unknown/non-ICR synchronous device transaction. If the source cannot be read, the CPU ICR remains unchanged.
- `arcaderecomp/i960_cpp.py`: emits `SYNMOV` as ahead-of-time native C++ without decoding the i960 opcode at runtime.
- `tests/test_i960_icr.py`: synthetic native tests for reset value, word alignment, ICR updates, updated CC, missing bus, unmapped memory and strict refusal of ordinary synchronous writes.
- `tools/hotd1_icr_probe.cpp` and `tests/test_hotd1_icr_probe.py`: standalone isolated private-ROM verification and its entirely synthetic CI counterpart.

**Not done:** `SYNLD`, non-ICR synchronous device transactions, ICR-driven interrupt edge/event routing, original arcade interrupt timing, or a complete i960 interrupt exception mechanism.

## Original ROM isolated native result

On the independently verified original `hotdo` 2-MiB program image, the generated native C++ executed the **one original i960 instruction at `0x000006D4`**. Its inputs were set explicitly using the preceding static instructions (`g4=0xFF000004`, `g5=0x000006A8`). The measured result:

```text
old_icr=0xff000000 success=1
ip=0x6d8 new_icr=0xf0e0d0c cc=2
```

The **exact public repository tool** `tools/hotd1_icr_probe.cpp`, compiled against the ROM-free GitHub Actions source bundle and a private AOT translation generated from the original 2-MiB ROM, independently reproduced this outcome with **process exit code 0**. The reconstructed original ROM SHA-256 matched `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`. In that isolated codegen experiment, **31 of 32 discovered nearby instruction addresses** emitted native code; these numbers are local to this test root only.

This is direct execution of the actual ROM's **compiled** `SYNMOV`, with a strict ROM-backed source memory read. It **does not** mean original arcade execution has passed the preceding `0x00F80000` board access. We deliberately did **not** skip or fake that address to reach the ICR.

## Reproduction (PRIVATE local user ROM)

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6d4 --limit 16384 --output build/hotd1/hotd1_i960.cpp
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_icr_probe.cpp -o build/hotd1/icr_probe
build/hotd1/icr_probe build/hotd1/maincpu.bin
```

The original ROM and derived CPU image/C++ remain private and **MUST NOT** be committed to the public repository. The probe deliberately isolates one original instruction and is not intended to bypass unimplemented real Model 2C hardware.

## Next proof gates

1. Identify `0x00F80000` by PCB-level documentation, trusted hardware traces or physical board instrumentation before assigning behavior.
2. Independently implement the actual INT0–INT3 interrupt routing, priority, memory tables and return mechanics with Intel-manual-backed tests.
3. Replace synthetic Sega serial-receiver data with original-board verified status and timing, then measure continuous original-ROM execution through this part of startup.
4. Complete Model 2C graphics, sound, video and original-arcade gameplay; see [our binding Model 2C completion criteria](MODEL2C_DEFINITION_OF_DONE.md).

**No Sega Model 2C completion announcement is warranted at this milestone.**
