# MC68000 bounded indirect jump-table startup advance

Status (2026-10-12): the original sound program's `JMP (A1)` dispatch is now
native AOT code without a run-time opcode decoder or an invented target.  The
same advance adds the two subsequently exposed ordinary MC68000 operations:
`MOVE d8(An,Xn),(Am)+` and register-to-register `OR.B/W/L`.

## Control-flow contract

`JMP (An)` consumes a fully known address register and sets the next program
counter.  Static discovery treats it as terminal: it neither assumes a
fallthrough nor guesses the register value.  The AOT API instead accepts
explicit additional instruction roots, validates that every root is an even
32-bit address, and emits only their statically discovered graphs.  A run-time
destination outside that generated set still reaches the dispatcher's
`untranslated_pc` stop on the next fetch.

For the authenticated EPR-19720 program, the exact sequence at `0x00600288`
masks the selector to even values `0..14`; the PC-indexed LEA at `0x00600292`
therefore limits A1 to the eight two-byte branch-table entries
`0x00600298..0x006002a6`.  The private explorer enrolls exactly those roots.
This proof supersedes the first observed A1 value (`0x006002a2`), which was
only one member of the table.

The indexed-source MOVE resolves and reads its complete source before using
the postincrement destination.  This preserves MC68000 alias behavior when a
base or index is also the destination register.  The increment commits only
after a successful destination write.  Register OR requires every consumed
bit known, preserves upper bits at byte/word widths, sets NZ, clears VC and
preserves X and its knownness.

Synthetic native sanitizer tests cover all address/data registers and widths,
source/destination aliases, word/long indexes, reserved extension bits,
knownness, flags, alignment and refused bus transactions.  The complete suite
result is recorded in the associated progress history entry and CI.

## Authenticated original-program evidence

All 257 exhaustive startup-state classes progress from the former
`JMP (A1)` boundary at 308040..308043 completed instructions to
313591..313594.  The generated graph contains 795 discovered and 795
translated instruction addresses, with no unsupported static opcode and no
discovery-limit hit.  The deeper original execution performs substantially
more initialization, including 303 COEF, 125 MADRS and 1737 MPRO writes.

The new common boundary is a 16-bit read by
`MOVE.W (A0)+,(A4)+` at PC `0x0060215c`:

```text
A0 = D2 = 0x00a9d9f4 (fully known)
A4 = 0x0000547c (fully known)
D6 = 0x000071a0 (fully known)
stop = bus_access, read width = 2
```

The public MAME Model 2 sound map places `0x00a00000..0x00dfffff` in banked
sample ROM and `0x00e00000..0x00ffffff` in its second bank.  It also documents
the direct `0x00800000..0x009fffff` sample window and the separate sound-RAM,
SCSP, control and audio-program regions.  Source:
[MAME Model 2 sound address map](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp#L2292-L2305).
The target manifest identifies the required original HOTD sample chips as
`mpr-19721.32` and `mpr-19722.34`. The original run did not supply them, so the
strict bus stopped rather than returning zeros or mirroring unrelated data.
Correction (2026-10-13): both private chips were already present in the parent
input directory, contrary to this document's earlier assertion. Both now
authenticate and resolve this read; see the [sample-backed result](SCSP_MIDI_INPUT.md).

## Identity-gated sample-ROM provider

`SoundROMBus` now optionally accepts the manifest's exact 8 MiB reconstructed
sample region.  It implements immutable byte and big-endian word reads across
the public map without broadening any write:

- `0x800000..0x9fffff` maps sample offsets `0x000000..0x1fffff`;
- `0xa00000..0xdfffff` maps offsets `0x200000..0x5fffff`; and
- `0xe00000..0xffffff` maps offsets `0x600000..0x7fffff`.

The experimental private explorer accepts the two sample chips only together,
authenticates their exact manifest sizes and SHA-1 identities independently of
filename/order, applies each chip's declared 16-bit byte swap, and keeps the
assembled region under ignored `build/`.  With no chips supplied, the same
read remains a strict bus fault and the report explicitly says the sample
region is unauthenticated.  Synthetic native tests cover every aperture edge,
physical 24-bit address masking, word endianness, absent/wrong-sized regions
and write refusal.

The sample-backed rerun now completes 498338..498341 instructions and reaches
unknown SCSP MIDI input at `0x100405`. Their bytes are not downloaded,
substituted or committed. Reset/empty-read evidence and board command transport
are the next sound boundary, not missing sample chips.
Sample playback, DSP execution, timing and audible output remain absent.
Estimates and Gates A/B/C do not change.
