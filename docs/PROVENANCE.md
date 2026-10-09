# HOTD1 provenance and authenticity

## Exact target

PRIMARY: **The House of the Dead** — the original **Sega Model 2C arcade release**, archived under **MAME short name hotdo**, catalogued **1997**.

Other historically important versions:
- **hotd** — Revision A, a later retail revision; secondary target.
- **hotdp** — prototype; planned after retail versions.
- Saturn, Windows and modern remake editions are secondary references, NOT the source of authenticity.

Original program chip signatures:
- epr-19696.15: 524288 bytes, CRC32 03da5623, SHA1 be0bd34a9216375c7204445f084f6c74c4d3b0c8.
- epr-19697.16: 524288 bytes, CRC32 a9722d87, SHA1 0b14f9a81272f79a5b294bc024711042c5fb2637.

Revision A changes these to epr-19696a.15 (CRC32 42adc32e) and epr-19697a.16 (CRC32 1e247cd5).

**A MAME parent/clone relationship describes ROM packaging, not release chronology.** Although hotdo is a clone of hotd for packing shared chips, original hotdo is the authoritative initial target.

## Source trail

- MAME ROM_START(hotdo) and ROM_START(hotd), source: https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp , collected 2026-10-08.
- Arcade Museum original arcade revision: https://www.arcade-museum.com/tech-center/machine/hotdo
- Arcade Museum Revision A: https://www.arcade-museum.com/tech-center/machine/hotd
- Sega arcade history (launch March 1997): https://www.sega.jp/history/arcade/

## Confidence boundaries

**Verified by reference inventory:** game identity, Model 2C board family, ROM chip sizes, per-chip CRC32/SHA1, interleaved region layouts.

**Not yet verified on actual ROM files:** any user-supplied archive; chip bytes must be scanned and compared. Merely naming a ZIP hotdo.zip is not verification.

**Not yet verified on original arcade hardware:** exact execution timing, graphics, lightgun responses, sound, and gameplay.

**Not implemented:** native recompilation of i960, Fujitsu TGPx4, or sound CPU. Region filling is a deterministic reconstruction convention, not a claim about actual uninitialized hardware state.

Original tooling and tests are independently authored. Published ROM wiring facts are cited; proprietary Sega game assets are not included.
