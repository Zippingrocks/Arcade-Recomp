# HOTD1 original arcade: i960KB reinitialization and second-stage entry

**Date:** 2026-10-08 Pacific / 2026-10-09 UTC  
**Status:** experimental original-ROM AOT execution, processor-state approximation pending independent hardware validation. **Sega Model 2C is NOT complete.**

## Source of truth

The input is the hash-verified **original `hotdo` Sega Model 2C arcade program**, not Revision A, the 1998 Windows PC port, or Saturn. Its reconstructed 2-MiB `maincpu` image has SHA-256:

`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`

No original chip bytes, game assets, or ROM-derived C++ output are committed to this repository.

Intel's original [80960KB Programmer's Reference Manual (1988)](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf), Chapter 7, pp. 7-10–7-15 and Chapter 13 p. 13-10, is the primary reference. Type `0x93` requests the processor to reload SAT/PRCB metadata and begin a new instruction sequence at the IP supplied in the fourth word.

## Original reinitialization evidence

The original IAC at the `SYNMOVQ` site `0x000006A0` supplies:

| Word | Data | Interpretation |
| --- | --- | --- |
| 0 | `0x93000000` | Reinitialize Processor |
| 1 | `0x00000000` | System Address Table address |
| 2 | `0x00510E00` | New Processor Control Block in work RAM |
| 3 | `0x000006B0` | New startup IP |

From the **actual original-ROM AOT run with deliberately simulated serial inputs**, the memory at the new RAM PRCB was inspected immediately before accepting the IAC:

| New PRCB field | Byte offset | Observed value |
| --- | --- | --- |
| Flags / control | `+0x04` | `0x0000000C` |
| Interrupt table | `+0x14` | `0x00510800` |
| Interrupt stack pointer | `+0x18` | `0x00510400` |
| Other initialization field | `+0x20` | `0x000001FF` |
| Other initialization field | `+0x24` | `0x0000027F` |
| Fault table | `+0x28` | `0x00000210` |
| Reserved | `+0x2C` | `0x00000000` |

**Compatibility discrepancy:** Intel's generic PRCB table describes a value of `0x27F` at *both* offsets `+0x20` and `+0x24`, while the verified original HOTD1 startup actually writes `0x1FF` at `+0x20`. The code **records** the field but does not prematurely reject this specific authentic arcade state. The control-flags word likewise requires validation; its values do not exactly match the manual's simplest reserved-bit assumptions.

## Code delivered

- `runtime/i960_reinitialize.hpp` — independent, **opt-in** two-stage implementation: read/validate PRCB fields without first mutating CPU state, then discard prior local register-frame cache, install new interrupt FP and IP, record the SAT/PRCB/interrupt/fault pointers, initialize supervisor/priority-31/interrupted process controls, and clear trace state.
- `runtime/i960_sync_runtime.hpp` — default behavior **still halts** after capturing the original IAC. Only an explicit developer opt-in allows CPU-stage transition.
- `arcaderecomp/i960.py` and `i960_cpp.py` — separate ahead-of-time entry roots so the reinitialize target `0x6B0` is compiled without inventing a normal branch edge. A post-reinitialize conditional branch cannot use stale pre-reset condition codes.
- `tests/test_i960_reinitialize.py` — compiled C++ tests for PRCB reload, new FP/IP, cache replacement, unchanged strict default behavior, bad alignment, unmapped PRCB read without partial state commit, undefined condition flags and post-IAC entry compilation.
- `tools/experimental/hotd1_fake_serial_reinit.cpp` — explicitly **fictional** serial-response fixture used solely to explore the program after an artificial receive-ready indication. It is not linked into the public native-game runtime.

## Reproduced original-ROM result

Two measured situations must not be conflated:

1. **Strict and authentic input boundaries:** The native code executes the original game's early startup instructions and accurately records TX2=`0xFF` and TX1=`0x01`, then halts at original IP `0x000A372C` because actual Sega 315-5649 RX-ready status has not been implemented. This is still our highest-confidence uninterrupted original-program result.
2. **Synthetic serial fixture (research only):** After substituting explicitly **invented** serial status and RX bytes, the verified original game's **translated native code executed 91,118 steps**, successfully applied IAC `0x93`, loaded **PRCB `0x00510E00`**, and entered the new code at **`0x000006B0`**. It then stopped at **`0x000006B4`**, a word store to **`0x00F80000`**, because that address is not yet documented in the strict Model 2C bus. There was exactly **one** processor reinitialization in this experiment.

This is real code execution with *fictional peripheral input*, **NOT proof** of arcade-equivalent I/O, correct reset cycle timing, audio/video boot, or full hardware compatibility.

## Reproduce locally

Use only a personally supplied, locally verified original `hotdo.7z` and a C++17 compiler:

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 --output build/hotd1/hotd1_i960.cpp

# The following probe USES ARTIFICIAL SERIAL BYTES. It is not arcade boot proof.
c++ -std=c++17 -O1 -Iruntime -Ibuild/hotd1 \
  tools/experimental/hotd1_fake_serial_reinit.cpp -o build/hotd1/fake_serial_probe
build/hotd1/fake_serial_probe build/hotd1/maincpu.bin
```

For **strict behavior**, continue using `tools/hotd1_strict_boot_probe.cpp` instead. Never force an always-ready `0x0C` status in the normal Model 2C runtime.

## Additional findings and remaining work

The genuine ROM code at `0x6B0` begins with `mov 2,g6`, followed by a store to **`0x00F80000`** at `0x6B4`. This device's function is **unknown and not implemented**; do not classify it as a watchdog or controller solely from its address. The subsequent `SYNMOV` at `0x000006D4` targeting Intel's on-chip interrupt-control register `0xFF000004` is **now implemented and tested in isolation against the verified original arcade ROM**: it installs ICR `0x0F0E0D0C` and advances to IP `0x000006D8`. This is not a claim that the authentic execution path passed the still-unmapped **`0x00F80000`** board write at `0x000006B4`. See [native Intel ICR test report](HOTD1_INTEL_ICR_STAGE2.md).

**Unresolved fidelity gates:** original 315-5649 serial timing/RX values, exact i960KB reinitialize register undefined-state semantics, SAT validations, external interrupt latch behavior, original board timing, `0x00F80000` register identity, ICR writes, dynamic-code discovery, MB86235 graphics, SCSP audio and all gameplay.

Completion rules remain in `docs/MODEL2C_DEFINITION_OF_DONE.md`. This milestone does **not** satisfy the complete Model 2C declaration.
