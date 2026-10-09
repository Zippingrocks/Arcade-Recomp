# HOTD1 original arcade dump audit — 2026-10-08

**Result: PASS — 29/29 documented ROM chips identified with exact size, CRC32 and SHA-1 matches.**

## Target and input

- Canonical MAME set: **hotdo** (original arcade revision; Sega Model 2C; 1997).
- Locally audited input: `hotdo.7z`, supplied for research.
- Archive member count: **29**.
- Total uncompressed member bytes: **88,604,672** (84.50 MiB).
- All 29 expected ROM filenames are present. No missing or extra ROM members.
- **No separate `hotd` parent archive required** to reconstruct the known `hotdo` memory regions.
- No proprietary ROM data was added to the repository.

## Key original-revision hashes

| Chip | CRC32 | SHA-1 |
| --- | --- | --- |
| epr-19696.15 | 03da5623 | be0bd34a9216375c7204445f084f6c74c4d3b0c8 |
| epr-19697.16 | a9722d87 | 0b14f9a81272f79a5b294bc024711042c5fb2637 |

Revision A would use different `epr-19696a.15` / `epr-19697a.16` code. This verified archive contains the originals.

The comparison uses the public MAME ROM inventory documented at https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp (`ROM_START(hotdo)`). The actual bytes were read from the user-supplied 7z through the system's libarchive library, hashed individually, and compared to those expected 29 records. This is a **chip-fingerprint audit**; it does not prove gameplay execution or cabinet timing.

## First boot-record research (private local reconstruction)

Following the published 32-bit paired-ROM wiring:
- i960 `maincpu` reconstructed image: 2,097,152 bytes; SHA-256 `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
- TGPx4 `copro_data` reconstructed image: 8,388,608 bytes with only the documented ROM-loaded lanes populated; SHA-256 `f5a77d7cbacfa341b80860792805ddea8362783e62bbea431d46d8308cfe1e6f`.
- i960 reset boot-record pointers read as little-endian words: PRCB = `0x000000B0`; initial instruction pointer = **`0x000005F0`**.
- Interrupt-stack pointer from PRCB + 24 = `0x00510400`.
- These starting addresses agree with the i960 initialization layout used in the public MAME i960 CPU core. They are starting evidence for the independent decoder, **not** a completed recompiler or verified original-hardware execution trace.

Model 2C startup, interrupt signaling, and instruction semantics need further independent validation before executing translated program code.

## Next technical milestone

Write independent i960KB instruction decoder and program-counter/control-flow unit tests around the original entry `0x5F0`, grounded in Intel's published architecture manuals. Do not copy implementations from other recompiler projects. Reconstruct graphics/audio hardware only after separately verified CPU invariants.

**Distribution policy:** all ROM archives, game-derived memory images, and proprietary assets remain private/local. Only factual hashes, analysis, code, and synthetic tests belong in this public repository.
