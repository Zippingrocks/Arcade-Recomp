# Original sound-control reference candidates

Date: 2026-10-11. This is static original-byte research, not a recovered
register implementation or an execution trace. The sound probe still
refuses the unknown byte write at `0x00400001`, PC `0x0060014c`.

## Reproducible audit

```sh
python -m arcaderecomp.sound_control_audit --chip /private/epr-19720.31 --output build/sound-control-references.json
python -m unittest discover -s tests -p test_sound_control_audit.py -v
```

The CLI verifies the original chip's manifest size, CRC32 and SHA-1 before
reconstruction. Its reconstructed region SHA-256 is
`36ee69f3f204a72699828d95f840ccded7d356ace7f5082f6a6cc06a14c81373`.
The public tests use artificial instructions and byte arrays only.

Every even offset is checked with the existing MC68000 decoder for supported
absolute MOVE stores and absolute LEA address materializations. A separate
scan records aligned 32-bit values matching the aperture after 24-bit bus
masking. These can occur in data or inside another instruction. The upper
byte is not exported as raw candidate data: only whether it is zero is recorded.

The audit independently labels membership in the translator's supported
static control-flow graph. That graph follows both conditional successors
and does not model device acceptance or actual branch outcomes. A candidate
in the graph is still not proven executed or an independently verified
instruction boundary. The graph's instruction cap is reported separately
from the complete even-offset pattern scan. Unsupported/indirect addressing,
computed pointers and embedded data prevent an all-references claim.

## Original-chip result

The authenticated scan identifies six syntactically valid direct byte-store
candidates, all to `0x00400001`:

| Candidate PC | Encoded source | Value established by this audit? |
| --- | --- | --- |
| `0x0060014c` | Immediate | Zero |
| `0x006001aa` | D1 | No |
| `0x006001f6` | D0 | No |
| `0x006004c6` | D1 | No |
| `0x006004dc` | D1 | No |
| `0x00600584` | D0 | No |

Only the first is in the currently supported startup graph. The separate
native probe has independently reached that attempted write; this offline
tool does not execute it. Do not infer that the remaining stores are zero
from the first write, or that any store is a no-op.

There are six aligned address values with a zero upper byte and three
additional masked-only matches. The latter are not promoted to pointers or
device references. No supported absolute LEA candidate names this aperture.
These negative results apply only to the declared patterns, not indirect
references or missing decoder forms.

## What remains unknown

The published [MAME Model 2 map and sound-control comments](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp)
associate this aperture with a board sound-control register but leave low
bits unresolved. That is third-party map evidence, not proof of original
hardware effects. No implementation was copied, and a zero-valued write
does not justify silently accepting it.

Next: establish instruction boundaries and source-register data flow around
the five additional candidates; find the matching Model 2C schematic or
independent decoder/latch observations, including byte strobes, reset state
and sample-ROM selects. The actual board control, sound reset wiring,
SCSP timing/audio and authentic main-CPU serial startup remain unresolved.

Tests cover syntactic data false positives, unknown register values, 24-bit
address masking, aligned versus odd candidates, truncation, input bounds,
separate graph/scan limits, original identity checks, metadata-only output,
input aliases (including links), and atomic replacement failure. No estimated
hardware percentage rises: sound-ROM execution stays 5%, audio 0%, Model 2C
20%, and overall original HOTD1 10%; Gates A/B/C remain open.
