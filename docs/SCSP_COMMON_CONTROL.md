# Bounded SCSP common control, not working audio

Status (2026-10-11): independently implemented register semantics and native
synthetic tests; no original-cabinet reset, timing or audio verification.

`runtime/scsp_common_control.hpp` models the first SCSP common-control word.
The PDF-reading review checked the actual register-table layout and access
annotations in Sega's [SCSP User's Manual ST-077-R2-052594](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf),
printed pages 5, 28, 35 and 88-89. Bits 9, 8 and 3:0 are MEM4MB, DAC18B and
MVOL respectively. These are write-only fields: their read result is zero,
not the last written value. Writes must keep other bits zero. Written-state
knownness is separate from readback; host initialization proves no reset value.

The chip-version nibble at bits 7:4 is not established for this Model 2C board.
The normal low-byte read therefore refuses until a caller explicitly provides
an observed version. Reserved high-byte readback also stays unknown; word reads
are refused. No zero version, reset-ready state, or reserved-bit value is assumed.

MC68000 CLR performs a read transaction before its write, but discards the
read data. The separate `Bus::read8_discard` contract preserves that transaction:
by default it calls the ordinary strict read. The optional SCSP implementation
accepts only the side-effect-free common-control word's byte addresses and
counts the discarded read without materializing unknown version/reserved bits.
It never extends that treatment to MIDI, interrupt status, or unknown devices.
The following zero write establishes MVOL=0, which Sega documents as mute in
its [sound-system description](https://www.infochunk.com/saturn/segahtml_en/hard/scsp/hon/p01_30.htm).
There is still no sample generator, mixer, DAC output or elapsed hardware time.

## Integration and evidence

`SoundROMBus` remains strict by default. Explicit
`enable_common_control_research(true)` allows only this bounded device model.
It also provides big-endian, aligned word reads of the published sound-ROM
aperture; word accesses are not decomposed into unverified byte transactions.

Run the authenticated private probe with the new opt-in:

```sh
python tools/experimental/hotdo_sound_bootstrap_probe.py --chip /private/epr-19720.31 --scsp-common-controls
```

The original `epr-19720.31` SHA-1 remains
`1edaed489a3518ddad85728e416319f940ea02bb`. Native execution with explicit vector
inputs completes 18 instructions, including one discarded SCSP control read
and one volume write, before attempting a byte write to `0x00400001`. The
separate [bounded original-HOTD sound-control contract](MODEL2_SOUND_CONTROL.md)
can now explicitly accept that proven low-lane transaction. With both models
enabled, the probe completes 32,795 instructions and refuses the next unknown
SCSP word at `0x00100402`. Ordinary consuming reads of the unknown chip version
remain refused even after the successful CLR.

Without the flag, the existing 17-instruction boundary at the SCSP read
`0x00100401` remains unchanged. Both modes are architecture-subset research
with caller-supplied vector contents, not independently observed cabinet boot.
Private reconstructed bytes and generated game C++ remain under ignored
`build/`; only metadata is printed.

The three ROM-free native tests enumerate all 65,536 word-write values, all
byte-write values on both lanes, explicit version values, state invalidation,
write-only readback, refused/read-discard distinctions, strict defaults,
unknown-device refusal and word alignment/endian boundaries. They run with
GCC and Clang when available, with undefined-behavior checks.

Next requirements: establish the remaining sound-board bit/strobe behavior,
reset wiring and sequencing; implement the `0x00100402` SCSP word from primary
documentation, then SCSP audio/timing and more sound CPU instructions. These
small register models alone do not justify increasing
the SCSP or overall audio estimate above 0%, or original HOTD1 above 10%.

The [sound-control reference audit](SOUND_CONTROL_REFERENCE_AUDIT.md) now
identifies six direct-store candidates without accepting this unknown device
or claiming that syntactic matches are executed instructions.
