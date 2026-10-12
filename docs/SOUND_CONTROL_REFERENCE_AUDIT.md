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

At the initial audit checkpoint, only the first was in the supported startup graph. The separate
native probe has independently reached that attempted write; this offline
tool does not execute it. Do not infer that the remaining stores are zero
from the first write, or that any store is a no-op.

After native immediate logic support, the first two candidates are in the
48-site supported graph. The metadata-only audit still does not infer D1.
Separate [original-byte native checks](M68000_IMMEDIATE_LOGIC.md) establish
an attempted value `0x08` at `0x6001AA` after isolated entry `0x60018C`,
using synthetic memory and retaining refusal of that board write. Four
independent supplied-state checks also derive `08/0C/0E/0F` from supplied
D0 bytes `F0/78/3C/1E`; they do not prove accepted writes or hardware effects.
The earlier continuous bootstrap stop at `0x60014C` is unchanged.

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

A separate first-hand [HOTD Model 2C-CRX repair report](https://forums.arcade-museum.com/threads/no-audio-sega-model-2c-crx-house-of-the-dead.543130/)
by Flocke28 (2024-10-14, posts 1–3) reports restored audio after moving JP1
from pins 1–2 to 2–3. This is a useful board-configuration observation,
not a bus trace or proof of any `0x400001` bit. Future sound captures should
record PCB revision and jumper positions. The JP1 nets and their possible
relationship to the control latch remain unverified; no runtime behavior
is inferred from this report.

Tests cover syntactic data false positives, unknown register values, 24-bit
address masking, aligned versus odd candidates, truncation, input bounds,
separate graph/scan limits, original identity checks, metadata-only output,
input aliases (including links), and atomic replacement failure. No estimated
hardware percentage rises: sound-ROM execution stays 5%, audio 0%, Model 2C
20%, and overall original HOTD1 10%; Gates A/B/C remain open.
