# Original HOTD1 `hotdo` — First measured native bootstrap trace

**Status:** ORIGINAL-ROM-TESTED, NOT arcade-reference-verified. **Model 2C incomplete.**

Local research date: 2026-10-08 (U.S. Pacific) / 2026-10-09 UTC.

## Exact private input

- User-provided original `hotdo.7z`: **29 of 29** documented original Sega Model 2C ROM chip entries matched by **size + CRC32 + SHA-1**. Revision A chip fingerprints were *not* substituted.
- Reconstructed original Intel i960 `maincpu`: 2,097,152 bytes, SHA-256 `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
- Intel i960 reset record: initial IP `0x000005f0`, PRCB `0x000000b0`, initial FP `0x00510400`.
- The public repository contains **no ROM bytes, compiled ROM-derived executables, generated proprietary disassembly dumps or assets**.

## First actual-original-ROM AOT execution

Using ArcadeRecomp's own ROM reader, region wiring, i960 decoder, C++ emitter, i960 local-frame runtime and strict Model 2C memory bus:

| Observation | Strict hardware mode | Opt-in documented serial TX mode |
| --- | --- | --- |
| Translated original i960 starting IP | `0x000005f0` | `0x000005f0` |
| Native translated instruction executions before stopping | 1,904 | **1,910** |
| Dynamic stop instruction address | `0x000a375c` | **`0x000a372c`** |
| Stop reason | Unimplemented serial write at `0x01c00014` | **Unimplemented serial status read at `0x01c0001a`** |
| Recorded channel 2 TX (`0x01c00014`) | disabled | `0xff` |
| Recorded channel 1 TX (`0x01c00012`) | disabled | `0x01` |
| CPU frame depth at halt | 1 | 2 |
| Model2C wait-state control writes counted | 14 | 14 |
| Default status/receive data invented | **no** | **no** |

The native probe *genuinely executed compiled operations lifted ahead of time from the original arcade i960 program*. The control register writes are only recorded with deterministic backing storage: authentic wait-state timing and interrupts are **not implemented**. The stop address `0x000a372c` is inside the original program's serial-status waiting function.

The result is **not a playable title screen**, **not a complete boot**, **not complete i960 hardware**, and **not completed Model 2C**. The native CPU step count is a dynamic count, not distinct instruction coverage.

## Discoverable original i960 instruction scope

Independent static graph discovery from original IP found **130 unique instruction addresses**. The original milestone translated **125** of them (5 unsupported). Subsequently, Intel-manual-backed native bit instructions and comparison/decrement lowered the count to **129 translated**, **1 unsupported** at the time of this initial measurement, the remaining original address:

- `0x000006a0` — `synmovq`: subsequently **decoded and given a native, fail-closed IAC capture**; Intel's KB manual proves it submits a `0x93` reinitialize message. **Full CPU reinitialization remains unresolved.** See [the newer IAC milestone](HOTD1_SYN_MOV_IAC.md).

A local rerun with that newly committed instruction code verified the same 1,910 original-ROM steps and the same precise serial-status fault. Later static code and peripheral boot paths still need wider discovery as new correct hardware behavior becomes available. **Current code generation reaches 130/130 addresses in this early bootstrap graph only; the SYNMOVQ site deliberately stops on pending IAC — it does not complete the CPU reinit. None of these figures represents full game or hardware completion.**

## Reproduce with a legitimately held original arcade set

No original ROMs are fetched by the repository, source CI, or published artifacts. `hotdo.7z` is supplied locally:

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --output build/hotd1/hotd1_i960.cpp --limit 8192
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 5000
build/hotd1/strict_probe build/hotd1/maincpu.bin 5000 --serial-tx
```

The first run should stop on an unknown serial TX write; the second opts into **documented TX bytes only** and should stop on serial status until an externally verified hardware/status provider exists. Both diagnostic exits are intentional and are not test-suite regressions. The private derived `maincpu.bin` and `hotd1_i960.cpp` must not be distributed.

## Why we will not emulate a shortcut

The original code writes `0xff` to RS422 channel 2 and `0x01` to channel 1, then polls the serial-status byte with a `0x0c` receive-ready mask. We do not return a hardcoded `0x0c` or fabricated gun position merely to push execution past this point. An optional *synthetic* status provider exists **only for tests and future external hardware trace integration**; it is not wired to the real original ROM probe by default.

See [315-5649 serial I/O research](SEGA_IO3155649.md), [CPU frame research](I960_FRAMES.md), [definition of completed Model 2C](MODEL2C_DEFINITION_OF_DONE.md) and [actual project roadmap](ROADMAP.md).

## Independent reference sources

- [Public MAME Model 2C address map and chip layout facts](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp) (not copied implementation).
- [Sega 315-5649 device register catalogue](https://github.com/mamedev/mame/blob/master/src/mame/sega/315_5649.cpp) (research only).
- [Intel 80960KB Programmer's Reference Manual, March 1988](https://www.bitsavers.org/components/intel/i960/80960KB_Programmers_Reference_Manual_Mar88.pdf).
- [Intel i960 Hx Developer's Manual, instruction-reference sections for shared base instruction meanings](https://datasheets.chipdb.org/Intel/80960/manuals/27248402.pdf). Architecture-specific Hx material is not substituted for KB-specific processor details.

**Acceptance:** original i960 bootstrap progress is now demonstrated. Full CPU/Model2C completion remains OPEN.
