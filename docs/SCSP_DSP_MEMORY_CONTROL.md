# SCSP DSP ring-buffer memory control

Status (2026-10-12): primary-manual-backed register semantics, exhaustive
synthetic native tests and authenticated original-ROM execution; no audio or
arcade-PCB timing validation.

The second SCSP common-control word at sound-CPU address `0x00100402` selects
the DSP effect ring buffer. Sega's
[SCSP User's Manual ST-077-R2-052594](https://antime.kapsi.fi/sega/files/ST-077-R2-052594.pdf),
section 4.3, defines two write-only fields:

| Word bits | Field | Meaning |
| --- | --- | --- |
| `8:7` | RBL | ring-buffer length code: 8K, 16K, 32K or 64K words |
| `6:0` | RBP | byte-address bits `19:13`, a 4K-word boundary |

Bits `15:9` are not assigned to these fields. `DspMemoryControl` therefore
accepts only values within mask `0x01ff`; a set reserved bit refuses the whole
transaction without changing recorded state. Byte writes preserve the other
lane's knownness. The register exposes no read path because both documented
fields are write-only, and no reset value is inferred from host initialization.

The original startup writes `0x0138`. This decodes to RBL code 2 (32K words)
and RBP `0x38` (byte address `0x70000`). Its 64 KiB byte span ends exactly at
`0x80000`, the limit of the documented 512 KiB sound RAM. This calculation is
configuration metadata; no DSP delay line, memory arbitration or effect
processing is implemented.

## Validation and next boundary

ROM-free tests enumerate all 65,536 word values and all byte values on both
lanes. They check accepted masks, partial knownness, invalidation, all four
length codes, base-address calculation, the exact original value, denied
readback and integration with the strict sound bus. GCC and Clang run with
warnings as errors and undefined-behavior checks.

The authenticated `epr-19720.31` probe, with the separately bounded SCSP and
Model 2 controls explicitly enabled, reports:

```text
completed instructions: 32797
DSP-memory-control writes: 1
written value / known mask: 0x0138 / 0x01ff
next refusal: word read at 0x00000c08, PC 0x00600174
```

The prior boundary was 32,795 instructions at the `0x100402` write. The two
newly completed instructions are that register write and a following `CLR.L
D4`. The next dependency is ordinary sound RAM, not another invented device
reply. Default strict execution still stops at the earlier `0x100401` SCSP
read after 17 instructions.

This work does not establish sound-board reset-vector wiring, SCSP reset
timing, DSP execution, MIDI, interrupts, synthesis, mixing or audible output.
SCSP remains at the 0% estimate, sound-ROM execution at 5%, and overall
original HOTD1 at ~10%; Gates A/B/C remain open.
