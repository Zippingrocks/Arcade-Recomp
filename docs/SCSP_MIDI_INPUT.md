# SCSP MIDI input and authenticated sample-ROM advance

Status (2026-10-13): bounded four-byte input FIFO and its interrupt transitions
are implemented; original startup still stops on unknown receive data. This
is not a main-CPU command link, timed serial device, or audible sound output.

## Source and bounded contract

Sega's [SCSP User's Manual ST-077-R2-052594](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf),
sections 4.2.4 and 4.2.12, printed pages 90 and 98 (PDF pages 102 and 110),
defines a four-byte input FIFO, read-only `MIBUF[7:0]`, an input request when
empty becomes nonempty, and automatic request release when all data is read.
The register diagrams were visually checked using the PDF-reading workflow;
the separate sound/main interrupt factors both use bit 3.

`runtime/scsp_midi_input.hpp` models only completed, externally supplied byte
events and successful byte consumption. Construction leaves occupancy unknown.
An explicit `establish_empty_research()` premise is required before enqueueing;
it is **not evidence of Model 2C reset state**. Values are kept in arrival order
across wrap-around. Unknown and empty reads refuse without changing state or
supplying a stale/zero byte. A full FIFO refuses a fifth receive event *before
applying it*: the caller must stop. Overflow retention and flag-clear behavior
are outside this model; refusal does not mean real hardware discards that byte.

The sound bus exposes the consuming low-byte lane at `0x100405` only after
explicit MIDI-input opt-in. A discarded byte read still consumes a supplied
byte. Word/high-byte/status reads and output writes remain unsupported because
reserved bits, output-FIFO state, and overflow behavior have not been modeled.
The implementation does not invent these fields to complete a bus word.

The first arrival requests bit 3 for both interrupt targets; draining the last
byte releases that factor without changing other pending/known bits. Establishing
the explicit empty premise also establishes that request as inactive. These
events do not count as guest interrupt-register writes. Enabling MIDI input
also enables fail-closed CPU interrupt observation even if common-control
register research was not separately enabled. It never assumes unknown control
registers are zero. Main-CPU interrupt delivery and serial timing remain absent.

Synthetic native tests cover all 256 data bytes, ring wrap, every occupancy,
unknown/empty/full refusals, bus-width/lane isolation, disabled access,
discard side effects, both interrupt targets, unrelated request preservation,
and four AOT byte reads with zero through four explicitly supplied bytes.
Tests use GCC and Clang with undefined-behavior sanitizers when available.

## Correction and original-byte evidence

Earlier documentation incorrectly said the two original sample chips were not
present in the workspace. On 2026-10-13, both were found in the parent input
directory and authenticated against the manifest. No download or substitute
was needed; earlier historical progress entries are retained unchanged.

| Input | Size | SHA-1 |
| --- | ---: | --- |
| `epr-19720.31` | 512 KiB | `1edaed489a3518ddad85728e416319f940ea02bb` |
| `mpr-19721.32` | 4 MiB | `6836973a687c59dd80f8e6c30d33155e306be199` |
| `mpr-19722.34` | 4 MiB | `405a892bc368ba862ba71bda7525b421d6973c0e` |

The identity-gated explorer word-swaps each sample chip as declared by the
manifest, then reruns every bounded startup-signature class. All 257 classes
(258 representative runs) advance from 313591..313594 to
**498338 / 498340 / 498341 completed instructions**, depending on route. The
result has all **524288 sound-RAM bytes known** after execution under the
explicit startup-signature premises; the harness does not initialize the
entire RAM to zero. The graph remains 795 discovered and
795 translated addresses with no unsupported static opcode or discovery limit.

The common boundary is now:

```text
PC 0x006001fc: byte read of MIBUF
address 0x00100405, stop bus_access, width 1
```

The program performs four consecutive receive reads before lowering SR's
interrupt mask. No receive data or occupancy evidence is supplied by this
probe, so it stops on the first read even with the bounded FIFO enabled. The
manual does not establish a defined value for an empty MIBUF read. Supplying
four arbitrary bytes would be a hypothetical scenario, not an authentic boot.
The sample-ROM advance is genuine original-byte execution under the existing
explicit startup-state premises, **not cabinet-reference or continuous boot
proof**, and is separate from the synthetic FIFO implementation evidence.

Reproduce privately with:

```sh
python tools/experimental/hotdo_sound_signature_explorer.py \
  --chip /private/epr-19720.31 \
  --sample-chips /private/mpr-19721.32 /private/mpr-19722.34
```

Inputs, reconstructed data and generated game C++ stay under ignored `build/`.
Next evidence needed: actual reset/empty-read behavior and the Model 2C command
transport; independent main-CPU 315-5649 serial status remains the platform boot
blocker. Timed synthesis, graphics, gameplay and Gates A/B/C remain open.
Estimates remain sound-ROM execution 10%, SCSP 0%, audio 0%, overall HOTD1 10%.
