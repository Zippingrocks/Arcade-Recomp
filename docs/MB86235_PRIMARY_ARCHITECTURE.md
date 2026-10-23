# Fujitsu MB86235/TGPx4 primary architecture evidence

**Status (2026-10-22): primary-document architecture research plus a
ROM-free structural decoder for the one published instruction format. No
MB86235 operation is decoded, translated, or executed.**

## Sources and scope

The strongest newly located source is Makoto Awaga's Fujitsu presentation,
**“3D Graphics Processor Chip Set,”** presented at Hot Chips VII in August
1995. Sega Retro indexes a 14-page scan and hosts the original PDF:

- https://segaretro.org/File:3DGraphicsProcessorChipSet.pdf
- https://retrocdn.net/images/d/d3/3DGraphicsProcessorChipSet.pdf

A later Fujitsu Science and Technology Journal paper, **“3D-CG System with
Video Texturing for Personal Computers,”** independently describes a system
which loads microcode into an MB86235 and passes its packet output to an
MB86271 renderer:

- https://segaretro.org/File:3D-CG_System_with_Video_Texturing.pdf
- https://retrocdn.net/images/c/c1/3D-CG_System_with_Video_Texturing.pdf

These are Fujitsu-authored descriptions of the component family, not a Sega
Model 2C service manual and not an observation of a House of the Dead board.
They establish chip architecture; they do not establish Sega wiring, reset
state, program contents, host half ordering, FIFO timing, or raster results.

## Directly documented MB86235 facts

The Hot Chips block diagrams document:

- 8K words by 64 bits of instruction RAM;
- two 1K-word by 32-bit data RAM banks plus an external-memory interface;
- 32-bit input and output FIFOs;
- separate floating-point multiply and floating-point add/ALU paths;
- MA0..MA7, MB0..MB7, AA0..AA7, and AB0..AB7 execution registers;
- 24 32-bit parameter registers addressed through separate read and write
  pointers; and
- a 64-bit Type-1 instruction divided into bits 63..61 = `000`, ALU field
  60..42, multiply field 41..27, and transfer field 26..0.

The same deck shows assembly-like examples using names such as `XOR`,
`FADD`, `FMUL`, and `MOV1`, but it does **not** supply the numeric subfield
encoding table needed to map arbitrary field values to those operations.
The repository therefore records the field partition without assigning any
operation meaning to the extracted integers.

The Fujitsu journal paper corroborates a programmable pipeline: an OpenGL
driver loads MB86235 and MB86271 microcode, packet data reaches the MB86235,
the MB86235 performs slope calculations, and it sends packet data onward to
the MB86271. This is useful architectural corroboration, not proof that Sega
uses the identical board-level protocol or microcode.

## Additional-source audit (2026-10-22)

The following sources were checked after the initial architecture recovery:

- [IEEE Micro 15(6), pages 37–45](https://doi.org/10.1109/40.476257), DOI
  `10.1109/40.476257`, is the expanded
  Fujitsu article **“3D graphics processor chip set.”** Crossref confirms the
  bibliographic record. [OpenAlex](https://openalex.org/W2159857691) currently
  marks it closed access, reports no
  repository full text, and provides no open PDF. It has therefore not been
  used as unseen opcode evidence. A lawfully obtained copy remains a useful
  realistic input for this project.
- Fujitsu patent family priority 1994-12-01, represented in English by
  [US6388671B1](https://patents.google.com/patent/US6388671B1/en), shares
  authors Hideki Yoshizawa, Tatsushi Ohtsuka, and Shigeru
  Sasaki with the chip-set article. It describes a four-stage
  fetch/decode/read/execute pipeline and a three-field instruction system
  controlling main, auxiliary, and dedicated graphics units. The patent does
  **not** identify that instruction as the MB86235 Type-1 word and publishes
  no numeric MB86235 sub-opcode table. Its fields must not be conflated with
  the Hot Chips ALU/multiply/transfer partition.
- The public [Bitsavers Fujitsu archive](https://bitsavers.trailing-edge.com/components/fujitsu/)
  and its [1996 North American IC catalog](https://bitsavers.trailing-edge.com/components/fujitsu/CD/1996_IC_Catalog/)
  index were checked. The catalog does not list MB86235 or a DSP/graphics
  programming-manual section. This is a documented negative result, not proof
  that no manual was ever issued.

These checks narrow the next source request to a complete MB86235 programming
manual, a lawful copy of the IEEE article, a Fujitsu development-tool manual
or assembler table, or an authentic program/cabinet capture. Patent
architecture alone cannot safely fill the numeric opcode gap.

## Privacy-preserving candidate triage

The offline candidate analyzer now counts the published three-bit format tag
for every packed 64-bit slot. Its metadata report contains an eight-bin
`format_tag_histogram`, documented-Type-1 and undocumented-format counts, and
an explicit false `mb86235_instruction_semantics_decoded` flag. It emits no
program word, subfield value, disassembly, or operation name.

This makes low-first/high-first host-word hypotheses mechanically comparable
as soon as a private candidate upload is supplied. A plausible distribution
can prioritize a hypothesis for further evidence; it cannot authenticate the
capture or prove that either ordering is correct.

## Implemented evidence boundary

[`arcaderecomp/tgpx4_isa.py`](../arcaderecomp/tgpx4_isa.py) accepts only an
explicit unsigned 64-bit integer whose three-bit format tag is `000`. It
returns the three opaque fields exactly at the published boundaries. Tags
`001` through `111`, non-integers, negative values, and oversized values fail
closed.

[`tests/test_tgpx4_isa.py`](../tests/test_tgpx4_isa.py) uses invented words
only. It checks each boundary bit, full-width masks, every undocumented tag,
and invalid input types. Passing these tests proves the independent decoder
matches the published diagram; it does not prove instruction semantics,
original program identity, or arcade behavior.

## Remaining blockers

1. Locate a complete Fujitsu MB86235 programming manual or equivalent
   primary opcode tables for the ALU, multiply, transfer, branch, and other
   instruction formats.
2. Capture or derive the private original HOTD1 program upload with explicit
   ordering, bounds, entry point, and control state.
3. Implement instruction semantics and a separate native AOT code generator,
   rejecting every unknown encoding.
4. Recover Sega's MB86271/MB86272 packet and memory interface and compare
   geometry/raster output against independent original-board captures.

Until those exist, `graphics.aot`, geometry execution, and rendering remain
unimplemented and Gates A/B/C remain open.
