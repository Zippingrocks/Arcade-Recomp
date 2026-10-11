# Model 2C MB86235 / TGPx4 — candidate program upload staging

**Status (2026-10-10): independently implemented offline word packing,
ROM-free synthetic tests only. No geometry DSP instruction has been decoded,
translated or run. No original-cabinet TGPx4 program capture has been checked.**

## Why this is a separate program

The original Sega Model 2C carries Fujitsu MB86235 geometry coprocessor
hardware, distinct from the older TGP in Models 1, 2 and 2A and the SHARC
implementation of Model 2B. Do not reuse those instruction decoders for 2C.

Public Model 2C hardware descriptions identify a dedicated geometry
coprocessor *program RAM* and a separate `copro_data` ROM region.
They also identify a host path supplying 32-bit upload words that build
candidate 64-bit coprocessor program entries. These are architectural
reference facts, **not** independently measured HOTD1 cabinet behavior.

The `copro_data` chips `epr-19707.29` and `epr-19706.30` are represented
by the existing original `hotdo` ROM manifest. This ROM *data* must not be
confused with an independently identified uploaded *program*. Neither
reconstruction of the ROM data nor packing 32-bit host writes is TGPx4
instruction decoding.

References (research only; implementation written independently):
- https://wiki.mamedev.org/index.php/TGP:Index (distinguishes TGPx4 from TGP)
- https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp
  (public Model 2C host upload arrangement and coprocessor memory map)
- [Original `hotdo` manifest](../targets/hotd1/original.json)

## Delivered offline capture tool

`arcaderecomp/tgpx4_program.py` accepts **only a contiguous externally
provided byte capture of host 32-bit words**, not raw RS-422 bytes or the
`copro_data` ROM image. The caller must specify:

- the *expected* even number of 32-bit writes (not inferred from file length);
- the input word endianness (little or big);
- whether the first write supplies the candidate 64-bit low or high half;
- a bounded source note and an explicitly unverified provenance label.

The two halves are packed into canonical **little-endian 64-bit candidate
slots**, with no zero padding, guessed missing writes, opcode interpretation,
or CPU/device side effects. The command line emits only counts and SHA-256
fingerprints, no program bytes, inferred opcodes or proprietary content.
The source note itself is hashed in exported metadata.

The 16,384-word bound is a file safety limit, **not** a claim about TGPx4
physical instruction RAM capacity. Published address spans are not a proof
of accessible words, reset behavior or actual uploaded program length.
An independently captured start/end/expected-write count remains required.

### Private workflow

Example using **invented, locally captured host-write binary**, not supplied
by this repository:

```sh
python -m arcaderecomp.tgpx4_program \
  --input /private/tgpx4-host-writes.bin \
  --output /private/tgpx4-metadata.json \
  --expected-dwords 1024 \
  --word-endian little --pair-order low-first \
  --provenance external_capture_unverified \
  --source-note "Board, acquisition method, and bounded capture window"
```

The example count and word pairing are *illustrative assumptions*, not a
verified HOTD1 upload length or confirmed cabinet halfword order. Alternative
`high-first` and `big` paths remain explicit for differential captures.
The CLI refuses incomplete pairs, count mismatches, oversized input,
unsupported provenance claims and output paths aliasing the evidence input.

Regression (synthetic, no Sega code or ROMs):
```sh
python -m unittest discover -s tests -p test_tgpx4_program.py -v
```

## Next requirements for native geometry recompiler

1. Capture or derive the original *host program upload* independently from
   i960-side native game execution (not from the unrelated `copro_data`
   region), preserving ordering and start/end conditions.
2. Confirm observed half ordering, program RAM range, entry point and
   control-register semantics against original hardware.
3. Establish the **MB86235's own 64-bit opcode fields** with independent
   instruction documentation and mutation tests. Unknown encodings must
   fail closed.
4. Implement a separate ahead-of-time MB86235 decoder/translator and
   compare its geometry command output with original-cabinet captures.

These steps are incomplete. CPU-visible geometry accesses still fault
under `StrictBus` and all Model 2C completion gates stay open.
