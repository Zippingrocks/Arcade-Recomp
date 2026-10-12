# Model 2 sound RAM with explicit knownness

Status (2026-10-12): mapped and synthetic-native tested; authentic power-on
contents and physical reset-vector wiring remain unknown.

The published [Model 2 sound map](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp)
places 512 KiB of shared 68000/SCSP RAM at `0x000000..0x07ffff`.
`runtime/m68k_sound_ram.hpp` implements that exact aperture without assuming
that freshly allocated host memory represents physical power-on RAM.

Each byte has independent value knownness:

- normal byte and big-endian word reads succeed only when every consumed byte
  has been established;
- byte/word writes establish exactly the bytes written;
- MC68000 CLR may perform its documented side-effect-free discarded read on
  unknown RAM and then establish the written zero; and
- invalidation removes all value knowledge without pretending to erase the
  physical array.

Odd or out-of-range word transactions fail. The sound bus remains strict by
default, and the RAM aperture requires an explicit research opt-in. ROM and
device apertures are not aliased into RAM. There is deliberately no implicit
zero fill, random fill, mirrored range, reset-vector copy or BERR exception
model.

## Tests and original boundary

ROM-free native tests cover both ends of the 512 KiB range, 24-bit physical
address masking, byte/word endianness, repeated writes, invalidation, disabled
mapping, unknown consuming reads and CLR byte/word/long transaction behavior.
GCC and Clang compile them with warnings as errors and undefined-behavior
checks.

The authenticated original sound program reaches PC `0x00600174` after
32,797 instructions and tries to read a word at `0x00000c08`. With strict RAM
enabled, all zero bytes are merely host storage and `sound_ram_known_bytes`
is still zero, so the read is refused. The nearby code compares two longwords
against the `ErrorSet` signature before deciding whether to preserve a byte
at `0x0c04`; silently returning zero would choose a startup history that has
not been observed.

The follow-up [exhaustive signature proof](M68000_SOUND_STARTUP_SIGNATURE.md)
now covers every possible value of bytes `0x0c04` and `0x0c08..0x0c0f` without
selecting a convenient reset value. All 257 resulting architectural classes
reach the same SCSP slot-register boundary after more than 262,000 instructions.

Sound reset, physical reset-vector wiring, SCSP synthesis, interrupts, timing
and audible output remain unresolved; Gates A/B/C are open.
