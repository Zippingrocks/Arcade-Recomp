# HOTD1 original i960 codegen coverage — widened static discovery

**Date:** 2026-10-09.  
**Status:** static codegen inventory, **not** execution coverage, original
arcade boot, or a measure of total Model 2C completion.

## Reproducible private-ROM input

- Original arcade `hotdo` game, **29/29** sizes, CRC32 and SHA-1 matches.
- Reconstructed 2-MiB i960 program SHA-256:
  `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
- ROM-free source from the public GitHub CI build at commit
  `9965b47bb321333b92764e372705f0ecd77d63e4`, including Intel
  `SYNLD`, opt-in Model 2C IRQ registers and BAL/BALX/BX native backends.
- Code graph rooted at reset IP `0x000005F0` plus the explicitly verified
  IAC reinitialize target `0x000006B0`, capped at 16,384 addresses.

## Static results

| Item | Count |
| --- | ---: |
| Discovered candidate instruction addresses | **3,051** |
| Addresses generating native C++ operations | **2,950** |
| Sites that deliberately fail closed | **101** |
| Rejected branch/entry targets | 0 |
| Discovery cap reached | No |

**These 3,051 locations are conservatively identified by current
static branch discovery, not proven to be original machine-executed
instructions.** Unrecognized opcodes, embedded tables, dynamic
branches and data/code ambiguity all limit this number. The apparent
`2,950 / 3,051` ratio is **not** a game completion percentage,
architecture-wide opcode-coverage statistic, or a claim that all
such code has executed correctly on a real Sega cabinet.

### Most common unsupported forms

These are *static-site* counts, not runtime frequencies:

| Operation/encoding | Distinct candidate sites |
| --- | ---: |
| `shri` | 16 |
| `stl` with MEMB addressing | 13 |
| `stq` with MEMB addressing | 11 |
| `ldq` with MEMB addressing | 8 |
| `movl` | 8 |
| `shrdi` | 7 |
| Completely unknown opcode | 6 |
| `bbc` | 5 |
| `ldl` with MEMB addressing | 5 |
| `stq` with MEMA addressing | 4 |
| `cmpinco` | 3 |

This suggests prioritizing **architecturally correct multi-register
loads/stores**, correct **arithmetic right shifts**, and tested bit
branches. Do not promote speculative implementations merely because
they reduce the count.

## Original-ROM dynamic regression: unchanged

Compiled native code from the same toolchain was run against the actual
private original program under the strict board bus:

- Default strict mode: **1,904 executed translated instructions**,
  stops at `0x000A375C` / write `0x01C00014` (serial TX disabled).
- Opt-in *documented TX only*: **1,910 executed translated
  instructions**, observes exactly TX2=`0xFF` and TX1=`0x01`, then
  halts at `0x000A372C` / read `0x01C0001A`.
- Both stops are deliberate unimplemented-device boundaries, not
  a complete authentic arcade boot. No synthetic serial RX/status was
  involved in these strict runs.

The earlier **91,118-instruction** post-IAC run remains a *separate,
explicitly fake serial-response diagnostic* and must not be counted as
arcade-reference verification. The `0x00F80000` stage-two board write
remains unknown and unimplemented.

## Reproduce without publishing Sega files

```bash
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp translate --layout targets/hotd1/original.json \
    --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 \
    --output build/hotd1/hotd1_i960.cpp
```

The generated source and source-chip data are **private, ROM-derived
research outputs**. Do not commit them to the public project.

Completion gate: [MODEL2C_DEFINITION_OF_DONE.md](MODEL2C_DEFINITION_OF_DONE.md).
