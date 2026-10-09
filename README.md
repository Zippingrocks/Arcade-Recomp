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

**M0 authenticated; M1 in progress; Sega Model 2C NOT COMPLETE.** The original `hotdo` archive passed all **29** chip fingerprints. Our independent Intel i960KB translator now handles local calls, a strict partial Model 2C bus, serial TX and an **opt-in Intel IAC `0x93` PRCB reinitialization** into the next ahead-of-time compiled entry. The **highest-confidence strict original-ROM execution** remains **1,910 translated native instructions**: TX2 `0xFF`, TX1 `0x01`, then an intentional stop at missing Sega 315-5649 receive status. Under **explicitly fabricated serial responses**, the genuine original game code executed **91,118 native instructions**, applied one IAC reinitialization to PRCB `0x00510E00`, entered `0x000006B0`, and correctly stopped at an unmapped `0x00F80000` word write in the next stage. The simulated-input run **does not demonstrate authentic arcade boot or gameplay**. I960 fault/interrupt handling, accurate IAC timing, real serial RX, other devices, MB86235/TGPx4 graphics, sound and full gameplay remain incomplete. See [measured stage-two findings](docs/HOTD1_IAC_REINITIALIZATION_STAGE2.md) and [strict original-ROM trace](docs/HOTD1_ORIGINAL_NATIVE_TRACE.md).

### Non-negotiable goals

- Preserve original arcade timing, gameplay, branching, enemy AI, gun input, video, music, sound, and presentation.
- Produce native ahead-of-time compiled game code, not an emulator disguised as a native game.
- Keep the arcade-faithful mode unchanged; ship modern improvements as separately selectable options.
- Research and implement our own pipeline. Other recompilers may inform methodology but no Daytona implementation is copied.
- Publish tools, tests, and factual hardware metadata, **never copyrighted Sega game ROMs, game assets, or generated ROM images**.

### ROM integrity check

Requirements: Python 3.10+ (standard library for ZIP, system libarchive for direct 7z). Native translation experiments additionally need a C++17 compiler. User supplies their own ROM archive; it is never uploaded to the public repository.

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /path/to/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /path/to/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp inspect --layout targets/hotd1/original.json --rom /path/to/hotdo.7z --count 40
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /path/to/hotdo.7z --output build/hotd1/hotd1_i960.cpp --limit 16384 --extra-entry 0x6b0
c++ -std=c++17 -O2 -Ibuild/hotd1 -Iruntime tools/hotd1_boot_probe.cpp -o build/hotd1/boot_probe
build/hotd1/boot_probe build/hotd1/maincpu.bin 500

# Strict alternative: no fabricated serial-I/O or unknown hardware responses.
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 \
  tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000
# Allow only independently documented Sega serial TRANSMITS; status stays strict.
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000 --serial-tx

# Separately test ONE original IAC instruction with known register inputs.
# This is NOT an actual full serial handshake or processor reboot.
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_iac_probe.cpp -o build/hotd1/iac_probe
build/hotd1/iac_probe build/hotd1/maincpu.bin

# Optional experimental stage-two CPU research, with explicitly FAKE
# Sega serial RX/status. NOT a faithful arcade game startup!
c++ -std=c++17 -O1 -Iruntime -Ibuild/hotd1 \
  tools/experimental/hotd1_fake_serial_reinit.cpp -o build/hotd1/fake_serial_probe
build/hotd1/fake_serial_probe build/hotd1/maincpu.bin
```

The parent archive is optional when the supplied archive contains all 29 original ROM chips. ZIP files are supported through the Python standard library. Direct 7z support uses the **system libarchive shared library** (available in many Linux distributions; other systems may require a separate install). If libarchive is unavailable, extract the 7z locally and repack as ZIP for auditing. Audit is an identity check, not an arcade emulator. **The strict native probe deliberately exits with code 3 when it reaches unimplemented hardware.** Code 4 denotes an unsupported translated CPU operation. Neither is evidence of arcade boot.

### Evidence

- MAME [`ROM_START(hotdo)`](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp) identifies the original revision and its machine architecture.
- [Arcade Museum original set inventory](https://www.arcade-museum.com/tech-center/machine/hotdo) documents chip IDs and checksums.
- [Sega arcade history](https://www.sega.jp/history/arcade/) dates the original arcade game's launch to March 1997.

**Completion is not subjective:** see [binding Model 2C definition of done](docs/MODEL2C_DEFINITION_OF_DONE.md). We will explicitly announce verified Gate A (CPU), Gate B (integrated platform), and Gate C (faithful original full-game completion), with the exact “SEGA MODEL 2C RECOMPILATION SUCCESSFULLY COMPLETED!” announcement reserved for Gate C.

Further: [verified processor reinitialization, limitations, stage-two hardware blocker](docs/HOTD1_IAC_REINITIALIZATION_STAGE2.md), [Intel 80960KB SYNMOVQ / original reinit IAC](docs/HOTD1_SYN_MOV_IAC.md), [verified original-ROM 1,910-step native execution](docs/HOTD1_ORIGINAL_NATIVE_TRACE.md), [Sega serial I/O](docs/SEGA_IO3155649.md), [original ROM audit](docs/HOTD1_ORIGINAL_AUDIT.md), [first native bootstrap experiment](docs/HOTD1_NATIVE_BOOT.md), [i960 KB procedure-frame research](docs/I960_FRAMES.md), [hardware research](docs/MODEL2C_HARDWARE.md), [strict Model 2C bus](runtime/model2c_bus.hpp), [provenance](docs/PROVENANCE.md) and [roadmap](docs/ROADMAP.md).