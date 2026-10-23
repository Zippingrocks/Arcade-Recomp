# Model 2C MB86235 / TGPx4 — candidate program upload staging

**Status (2026-10-22): independently implemented offline word packing and a
primary-source structural decoder for the published Type-1 field partition,
with ROM-free synthetic tests only. No geometry DSP operation has been
decoded, translated or run. No original-cabinet TGPx4 program capture has
been checked.**

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
- [Fujitsu MB86235 primary architecture evidence](MB86235_PRIMARY_ARCHITECTURE.md)
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


### CPU-side host-write capture audit (2026-10-10)

A separate offline audit, `arcaderecomp.tgpx4_host_trace`, accepts a
**filtered, order-preserving CPU-side write transcript** rather than assuming
an arbitrary raw binary is the uploaded program. A candidate upload must
contain exactly one *observed in the supplied transcript* control-on write
to `0x00980000`, an even number of full 32-bit writes to the documented
`0x00884000–0x00887FFF` TGPx4 FIFO aperture, and a final control-off write
to `0x00980000`. Control writes may differ only in bit 31. The parser
rejects anything else, including missing final control, gaps in ordinals,
unobserved writes, reported dropped events, and partial word pairs.

The following is an entirely **invented synthetic capture**. Hex words are
not original HOTD1 data:

```json
{
  "schema": "model2c-tgpx4-host-writes-v1",
  "provenance": "synthetic",
  "source_note": "Synthetic test only, no cabinet observation",
  "capture_complete": true,
  "total_events": 4,
  "dropped_events": 0,
  "events": [
    {"ordinal": 1, "direction": "write", "address": "0x00980000", "width": 4, "completed": true, "value": "0x80000000"},
    {"ordinal": 2, "direction": "write", "address": "0x00884000", "width": 4, "completed": true, "value": "0x11223344"},
    {"ordinal": 3, "direction": "write", "address": "0x00884004", "width": 4, "completed": true, "value": "0x55667788"},
    {"ordinal": 4, "direction": "write", "address": "0x00980000", "width": 4, "completed": true, "value": "0x00000000"}
  ]
}
```

```sh
python -m arcaderecomp.tgpx4_host_trace \
  --capture /private/cpu-writes.json \
  --output /private/tgpx4-trace-metadata.json \
  --pair-order low-first
```

The tool extracts 32-bit numeric writes in recorded order and fingerprints
candidate 64-bit slots by using the existing staging module. No binary is
exported. `capture_complete` and `provenance` are **source assertions**
that cannot authenticate real hardware or detect omitted events before
filtering; this requires independent capture evidence. Neither the strict
native bus (which still faults on these accesses), original startup, physical
control prior state, timing, the MB86235 opcode semantics, nor ROM correctness
are established by this tool.

### Evidence checklist for future original HOTD1 captures

Before interpreting any reported `candidate_sha256` as a meaningful game
program fingerprint, preserve three **private** independent checks:

1. The raw capture includes an observed start and end control write, with
   recording bounds and a known acquisition method, not a guessed reset.
2. The CPU-write capture mechanism reports its total/loss counters. A
   filtered stream must retain the original write order without silently
   removing mid-upload FIFO transactions.
3. Reproduce the digest from a second independent collection or from
   an appropriately authenticated original-code-derived upload trace.
   Agreement would corroborate *bytes and ordering* only, not MB86235
   instruction meaning or original-cabinet execution.

The current tools cannot perform those independent observations themselves.
Any missing check stays explicitly unresolved; never upgrade the
`external_capture_unverified` provenance label to hardware proof.

This input is an **externally obtained filtered CPU-write transcript**, not
an automatic native `StrictBus` trace. A complete authentic HOTD1 input
cannot yet be collected from uninterrupted native boot because the authentic
Sega 315-5649 RX/status boundary remains unresolved.

```sh
python -m unittest discover -s tests -p test_tgpx4_host_trace.py -v
```



### Native attempted-access trace — not an accepted upload

The strict `StrictBus` now provides an **opt-in**, bounded
`geometry_access_trace` recording attempted CPU reads/writes to the known
geometry and TGPx4 apertures, with ordinal and dropped-record accounting.
The private original-HOTD1 native boot probe accepts `--geometry-trace`
and emits `geometry_access` records followed by an explicit
`geometry_trace_summary` footer. This does not enable geometry hardware:
each strict geometry access still raises `DeviceAccessFault`. Attempted
write values are known but `completed=no`; denied read values remain
`UNOBSERVED`. Rejected synchronous non-RAM loads return Bad Access and do
not emit fabricated completed reads.

```sh
strict_boot_probe /private/maincpu.bin 10000 --serial-tx --geometry-trace
```

The separate accepted-upload auditor `tgpx4_host_trace` **must reject**
these attempted writes as incomplete. The strict original native boot still
stops at the unknown Sega 315-5649 status read, with no fake RX/status or
TGPx4 result. A diagnostic trace is not an arcade capture, not a decoded
MB86235 program, and not evidence of completed physical FIFO transactions.
ROM-free GCC/Clang tests cover the observer and a synthetic compiled boot
probe. No proprietary image, private generated code or DSP opcodes are
committed.


## Next requirements for native geometry recompiler

1. Capture or derive the original *host program upload* independently from
   i960-side native game execution (not from the unrelated `copro_data`
   region), preserving ordering and start/end conditions.
2. Confirm observed half ordering, program RAM range, entry point and
   control-register semantics against original hardware.
3. Extend the Fujitsu-documented **MB86235 64-bit Type-1 field partition**
   with primary numeric sub-opcode tables and the remaining instruction
   formats. The current structural decoder assigns no operation semantics;
   unknown formats fail closed.
4. Implement a separate ahead-of-time MB86235 decoder/translator and
   compare its geometry command output with original-cabinet captures.

These steps are incomplete. CPU-visible geometry accesses still fault
under `StrictBus` and all Model 2C completion gates stay open.
