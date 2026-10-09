# HOTD1 native bootstrap milestone (experimental)

Target: **original `hotdo` Sega Model 2C arcade program**. No Saturn, PC or Revision A code was used.

> **Historical bootstrap milestone.** The original 107-instruction experiment below
> has now been **superseded** by the reproducible
> [1,910-instruction original-ROM native I/O experiment](HOTD1_ORIGINAL_NATIVE_TRACE.md).
> That later result genuinely reaches the 315-5649 serial status read, but
> **Model 2C is still incomplete and the original game does not boot to play**.

## What was actually demonstrated

A private, ROM-derived set of native C++ operations was generated from the earliest reachable section of the original Intel i960 program. Compiled with a standard C++17 compiler, it executed the first **107 instructions** across **29 distinct instruction addresses**, observed **17 bus writes**, and stopped at the first CPU **call** instruction at **0x0000068C** (relative target **0x000A3750**). The CPU began at the actual ROM boot address **0x000005F0**.

The initial writes go to **0x00E00000**, which the published Model 2 board map describes as CPU control/wait-state registers. The experiment only logged those writes in a **shadow-memory diagnostic bus**, without simulating the hardware-specific effects. Its other external RAM regions were also defaulted to zero on first read. Therefore:

**PASS:** Generated native host code can execute a verified original-game startup slice with no runtime decoding of i960 opwords.

**Not achieved in that historical test:** Accurate hardware reset, i960 call/register frames, real wait-state effects, graphics output, audio, interrupts or full game execution. Some CPU-frame semantics were added subsequently; see the latest trace for current status.

This experiment is not a ROM-independent executable game and is not a claim that the original arcade game boots. The private machine-code inputs, emitted ROM-derived C++ and memory images are not in Git.

## Reproduce with your own verified `hotdo` archive

The following project commands audit the original ROM, reconstruct its i960 program, produce private native C++ and compile a diagnostic harness. They require Python 3.10+, a host C++17 compiler and libarchive for direct 7z support.

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp inspect --layout targets/hotd1/original.json --rom /private/hotdo.7z --count 40
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --output build/hotd1/hotd1_i960.cpp --limit 512
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_boot_probe.cpp -o build/hotd1/boot_probe
build/hotd1/boot_probe build/hotd1/maincpu.bin 500
```

The native probe supplies stand-in bus callbacks. A short original boot experiment should stop at the first unsupported call; the exact number of steps depends on the scope of the generated native control-flow graph. Any unsupported instructions stop execution deliberately, rather than being silently skipped.

## Next proof gates

1. Independently document i960KB `call`, `ret`, procedure-frame handling, interrupt initialization and the associated register file from Intel's manuals.
2. Provide synthetic native tests for nested calls and returns, then compare against documented i960 register-window behavior.
3. Build a typed, independently authored **Model 2C bus** rather than shadow RAM: ROM, work RAM, wait-state control, I/O, interrupt and geometry devices with traceable writes.
4. Introduce a trace comparator so native output can be evaluated against verified cabinet/emulator reference observations without publishing commercial bytes.

The mission remains **a standalone, faithful, ahead-of-time recompiled arcade game**, not an emulator shell.


## Current follow-up: native calls and strict bus

Since the historical 107-step experiment above:

- Our independently authored Intel 80960KB frame helper now compiles and
  exercises nested local `CALL`, `CALLX` and `RET`, including four-frame
  spill/reload behavior, against **synthetic** instruction streams.
- i960 arithmetic comparisons were corrected to use the documented
  three-bit `AC.cc` masks and proper `src1` versus `src2` order. Synthetic
  compiled tests cover every CTRL branch-mask outcome.
- Native `ldob`, `ldib`, `ldos`, `ldis`, `stob`, and `stos` now
  use width-specific memory-bus callbacks. Signed loads are sign extended.
- A new strict Model 2C host bus maps documented CPU ROM, working RAM,
  CPU control and optional game data, while rejecting unimplemented I/O,
  geometry, interrupt and timer hardware. No unknown peripheral reads return
  fabricated zeroes.
- A new **strict native diagnostic harness** replaces the fake shadow
  memory with that strict bus when requested, so unimplemented hardware is
  detected instead of silently bypassed.

The original ROM's `CALL` at `0x0000068C` targets `0x000A3750`.
Independent static analysis of the verified chip bytes confirms that early
in this callee, a `STOB` addresses `0x01C00014` — inside the Sega
315-5649 I/O controller window. Synthetic tests show our strict bus rejects
that address with a typed device fault.

**Original-ROM test now complete for this early segment:** the corrected
native recompiler was run against the verified original `hotdo` archive.
Its strict mode executes **1,904** compiled instructions before refusing
the original first serial TX. Enabling documented serial TX only allows
**1,910** compiled original instructions, records `0xff` (TX2) and
`0x01` (TX1), and then halts at `0x000a372c` on serial status.
Newly supported bit and compare-decrement opcodes brought this early graph
to **129 of 130** translated instruction addresses. The one remaining
`synmovq` operation still needs CPU/device investigation.
See [the full measured trace](HOTD1_ORIGINAL_NATIVE_TRACE.md).

**This is actual early original program execution, not proof of full arcade
boot, complete CPU behavior or a working Model 2C platform.**

To run the updated strict experiment locally, after generating the
private ROM and translated C++ files using the commands below:

```bash
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 \
  tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000 --serial-tx
```

The strict probe intentionally returns exit code **3** on an
unimplemented device and **4** on a missing i960 translation or unsupported
frame state. These are **expected, informative halts**, not passed boot tests.

Evidence and next steps: `docs/MODEL2C_HARDWARE.md`,
`docs/I960_FRAMES.md`, and `docs/MODEL2C_DEFINITION_OF_DONE.md`.
