# ArcadeRecomp

**Independent ahead-of-time recompilation research for classic arcade systems.**

## Project 001 — The House of the Dead (original arcade revision)

Our first and authoritative target is **Sega's original Model 2C arcade game**, as catalogued by MAME under **`hotdo`** (1997). This is **not** the Sega Saturn or Windows adaptation, the 2022 remake, or MAME's later **Revision A** parent set `hotd`.

| Revision | MAME ID | Role |
| --- | --- | --- |
| Original release | `hotdo` | **PRIMARY** |
| Revision A | `hotd` | Secondary retail baseline |
| Prototype | `hotdp` | Historical target after retail fidelity |

**Distinctive original-revision program ROMs** (from public MAME cataloguing):

- `epr-19696.15` — CRC32 `03da5623`, SHA-1 `be0bd34a9216375c7204445f084f6c74c4d3b0c8`
- `epr-19697.16` — CRC32 `a9722d87`, SHA-1 `0b14f9a81272f79a5b294bc024711042c5fb2637`

Revision A uses `epr-19696a.15` and `epr-19697a.16` instead. **Archive names alone do not establish authenticity; verify member hashes.** In MAME naming, `hotdo` is a clone of `hotd` for ROM-storage purposes, but **our project's primary target is still `hotdo`**.

### Current stage

**M0 — hardware and ROM research.** This repository is not a working recompiler or playable port. The initial independent utilities audit user-supplied ROM files, verify their chip hashes, and reconstruct known memory regions using documented chip wiring. Intel i960 translation, Fujitsu MB86235/TGPx4 support, original audio and native graphics execution remain future milestones.

### Non-negotiable goals

- Preserve original arcade timing, gameplay, branching, enemy AI, gun input, video, music, sound, and presentation.
- Produce native ahead-of-time compiled game code, not an emulator disguised as a native game.
- Keep the arcade-faithful mode unchanged; ship modern improvements as separately selectable options.
- Research and implement our own pipeline. Other recompilers may inform methodology but no Daytona implementation is copied.
- Publish tools, tests, and factual hardware metadata, **never copyrighted Sega game ROMs, game assets, or generated ROM images**.

### ROM integrity check

Requirements: Python 3.10+ (standard library only). User supplies their own arcade ROM archive; it is never uploaded to the public repository.

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /path/to/hotdo.zip --parent /path/to/hotd.zip
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /path/to/hotdo.zip --parent /path/to/hotd.zip --output build/original
```

The parent archive is optional when all required original ROM files are present in one non-merged archive. The initial tool supports standard ZIP files, including ZIPs containing MAME set subfolders. A `.7z` archive can be extracted locally into the documented ZIP/chip layout before auditing; native 7z support is a later task. Audit is an identification tool, not proof of circuit-level emulation.

### Evidence

- MAME [`ROM_START(hotdo)`](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp) identifies the original revision and its machine architecture.
- [Arcade Museum original set inventory](https://www.arcade-museum.com/tech-center/machine/hotdo) documents chip IDs and checksums.
- [Sega arcade history](https://www.sega.jp/history/arcade/) dates the original arcade game's launch to March 1997.

See `docs/PROVENANCE.md` and `docs/ROADMAP.md`.