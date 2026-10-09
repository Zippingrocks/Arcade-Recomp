# HOTD1 native bootstrap milestone (experimental)

Target: **original `hotdo` Sega Model 2C arcade program**. No Saturn, PC or Revision A code was used.

## What was actually demonstrated

A private, ROM-derived set of native C++ operations was generated from the earliest reachable section of the original Intel i960 program. Compiled with a standard C++17 compiler, it executed the first **107 instructions** across **29 distinct instruction addresses**, observed **17 bus writes**, and stopped at the first CPU **call** instruction at **0x0000068C** (relative target **0x000A3750**). The CPU began at the actual ROM boot address **0x000005F0**.

The initial writes go to **0x00E00000**, which the published Model 2 board map describes as CPU control/wait-state registers. The experiment only logged those writes in a **shadow-memory diagnostic bus**, without simulating the hardware-specific effects. Its other external RAM regions were also defaulted to zero on first read. Therefore:

**PASS:** Generated native host code can execute a verified original-game startup slice with no runtime decoding of i960 opwords.

**NOT YET PASS:** Accurate hardware reset, i960 call/register frames, real wait-state effects, graphics output, audio, interrupts or full game execution.

This experiment is not a ROM-independent executable game and is not a claim that the original arcade game boots. The private machine-code inputs, emitted ROM-derived C++ and memory images are not in Git.

## Reproduce with your own verified `hotdo` archive

The following project commands audit the original ROM, reconstruct its i960 program, produce private native C++ and compile a diagnostic harness. They require Python 3.10+, a host C++17 compiler and libarchive for direct 7z support.

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp inspect --layout targets/hotd1/original.json --rom /private/hotdo.7z --count 40
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --output build/hotd1/hotd1_i960.cpp --limit 512
c++ -std=c++17 -O2 -Ibuild/hotd1 tools/hotd1_boot_probe.cpp -o build/hotd1/boot_probe
build/hotd1/boot_probe build/hotd1/maincpu.bin 500
```

The native probe supplies stand-in bus callbacks. A short original boot experiment should stop at the first unsupported call; the exact number of steps depends on the scope of the generated native control-flow graph. Any unsupported instructions stop execution deliberately, rather than being silently skipped.

## Next proof gates

1. Independently document i960KB `call`, `ret`, procedure-frame handling, interrupt initialization and the associated register file from Intel's manuals.
2. Provide synthetic native tests for nested calls and returns, then compare against documented i960 register-window behavior.
3. Build a typed, independently authored **Model 2C bus** rather than shadow RAM: ROM, work RAM, wait-state control, I/O, interrupt and geometry devices with traceable writes.
4. Introduce a trace comparator so native output can be evaluated against verified cabinet/emulator reference observations without publishing commercial bytes.

The mission remains **a standalone, faithful, ahead-of-time recompiled arcade game**, not an emulator shell.
