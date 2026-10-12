# Bounded original-HOTD Model 2 sound control

Status (2026-10-12): synthetic tested and original-ROM exercised against a
public Model 2 reference model; not independently verified on an arcade PCB.

`runtime/model2_sound_control.hpp` implements the write-only transaction
contract needed by the original `hotdo` sound program at `0x00400000..01`.
It is deliberately narrower than a general Model 2 sound-board model.

## Evidence and boundary

The current [MAME Model 2 source](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp)
maps a 16-bit write handler at `0x400000..0x400001`. Its handler changes the
two sample-bank windows only when the sample region is larger than 8 MiB, and
its own comments state that no supported Model 2 game has more than 8 MiB.
The versioned original-HOTD manifest independently defines exactly 8 MiB in
`targets/hotd1/original.json`. Therefore this target's transaction has no
sample-bank change in that public reference behavior.

That is emulator-source evidence, not an oscilloscope or logic-analyzer trace
from a Model 2C PCB. The reference also labels control bits 3:0 unresolved.
Consequently the implementation:

- accepts all low-lane byte values at `0x400001`, the lane used by all six
  statically identified direct original-HOTD stores;
- accepts an aligned 16-bit transaction at `0x400000`, matching the mapped
  aperture;
- records transaction data and known lanes for validation, but exposes no
  readable latch and never claims an internal reset value;
- refuses the unestablished even/high byte transaction, every read, adjacent
  addresses and all control access unless the caller explicitly opts in; and
- reports that the original-HOTD 8 MiB sample bank did not change.

This is not a generic implementation for hypothetical sample regions larger
than 8 MiB. No unverified bank offsets or low-bit effects were imported.

## Validation

ROM-free native tests exhaust all 256 low-byte values and all 65,536 word
values. They verify strict-by-default behavior, 24-bit physical address
masking, denied reads and neighboring lanes, and a generated sequence matching
the original `MOVE.B #0,$400001` form. Both GCC and Clang compile the tests
with warnings as errors.

The private probe authenticated original chip `epr-19720.31` with SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`, reconstructed it from the checked
manifest, and used explicit reset-vector inputs. With both bounded control
models enabled:

```text
translated graph: 741 / 744 discovered instructions
completed instructions: 32795
accepted sound-control writes: 1 (low byte 0x00)
accepted SCSP control writes: 2
next refusal: word write at 0x00100402, PC 0x0060016c
```

The previous optional boundary was 18 instructions at the denied
`0x00400001` write. The ordinary strict probe still refuses the preceding
SCSP access after 17 instructions. Generated C++, reconstructed bytes and the
local chip image remain in ignored `build/` storage.

This result establishes neither physical reset sequencing nor audio output.
The next dependency exposed here was the SCSP word at `0x100402`. Its
[manual-defined ring-buffer fields](SCSP_DSP_MEMORY_CONTROL.md) are now modeled
separately, moving the continuous boundary to sound RAM at `0x00000c08`.
Sound RAM,
interrupts, MIDI transport, timing, synthesis, mixing and cabinet validation
remain unresolved. Audio stays at 0%, sound-ROM execution at 5%, and overall
original HOTD1 at the separately reviewed ~10% estimate.
