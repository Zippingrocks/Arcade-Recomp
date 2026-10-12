# Original HOTD1 sound CPU: first independent native AOT execution

Status (2026-10-11): the authenticated original sound ROM completes **17
MC68000 instructions through generated native C++**, then stops at its first
unimplemented SCSP access. This is an isolated CPU architecture test with
explicit reset-vector inputs, not an observed cabinet reset or working audio.

## Implementation

`arcaderecomp/m68k.py` and `arcaderecomp/m68k_cpp.py` form a separate sound CPU
decoder and ahead-of-time translator. Generated C++ dispatches fixed instruction
semantics by PC; it neither fetches nor interprets guest opcodes at runtime.
Unknown instructions and undiscovered PCs stop explicitly.

The supported MC68000 subset is:

- MOVE immediate to SR, restricted to supervisor mode, trace disabled and
  interrupt mask 7; unsupported control changes stop before modifying state.
- CLR byte/word/long to data registers; MOVEQ; MOVEA word/long from a data
  register; LEA absolute-long; NOP.
- BRA and Bcc byte/word displacements; DBcc with a word counter. BSR is not
  implemented. The MC68000 byte displacement `0xff` means -1, rather than the
  long-displacement extension used by later 680x0 processors.
- CLR byte at `(d16,An)`, preserving the MC68000's documented **read before
  clear** bus access. The runtime performs a read, then writes zero, then
  updates flags/PC. A denied read never causes a write.

The runtime tracks defined register bits and status bits. Reset does not invent
data-register or CCR values. Partial register clears preserve upper bits and
their definedness; MOVEA.W needs only the low source word. Instruction count is
a diagnostic count, not a hardware cycle estimate. There is no instruction
prefetch, asynchronous interrupt source, exception delivery, or cycle timing.

`SoundROMBus` implements only byte reads from the published sound-program ROM
aperture, `0x600000..0x67ffff`, with the MC68000's 24-bit external address.
Writes and other data addresses stop. Sound RAM initial contents, vector-copy
wiring, Yamaha SCSP registers, sample banks and sound-command transport are not
substituted with generic memory or assumed ready state.

## Original-byte evidence

The locally supplied `epr-19720.31` matches the original manifest's size, CRC32
and SHA-1 `1edaed489a3518ddad85728e416319f940ea02bb`. Existing manifest-driven
16-bit swapping constructs the sound program image. Its vector entries supply
the explicit architectural inputs SSP `0x00002000`, PC `0x00600120`.

The private native run completes initial status setup, data/address-register
initialization and an address load. It stops at PC **`0x00600148`** while
attempting the read portion of CLR.B at **`0x00100401`**, within the published
SCSP aperture. The final SR is `0x2704`, SSP is `0x2000`, and A5 is `0x100000`.
There are 17 completed instructions and **no accepted SCSP read or write**.
Static traversal finds 19 sites: 18 translated and one unsupported at
`0x0060014c`. These counts are neither sound coverage nor board fidelity.

This result starts from the authenticated ROM's vector contents supplied by
the caller. The actual board's vector availability at address zero and reset
sequencing remain unverified. No continuous main-CPU boot or audio output is
claimed, and the independent main CPU's serial-status blocker remains open.

## Reproduction and tests

Run the private probe using the legally supplied chip and a C++17 GCC/Clang
compiler:

```sh
python tools/experimental/hotdo_sound_bootstrap_probe.py --chip /private/epr-19720.31
```

The probe verifies the chip, reconstructs the region, generates and compiles
native code with undefined-behavior checks, then prints metadata. Proprietary
bytes and ROM-derived C++ remain in a fresh subdirectory of ignored
`build/m68k-sound-bootstrap/`. Existing outputs are not overwritten. Build
directory escapes are rejected. Never commit these private artifacts.

```sh
python -m unittest discover -s tests -p test_m68k_bootstrap_native.py -v
```

Public synthetic native tests cover immediate sign extension, register/size
fields, positive and negative MOVEA.W values, all branch conditions and CCR
combinations, DBcc termination/wrap, partial definedness, signed displacement,
24-bit data addressing, strict ROM boundaries, and read/write rejection order.
Rejected memory accesses preserve the PC and flags but cannot undo an already
completed external read; this is diagnostic refusal, not emulated bus-error
exception delivery. Both GCC and Clang run when available, with UBSan.

## Sources and next work

Instruction encodings and behavior are independently implemented from
[Motorola's M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf):
Bcc/BRA, CLR (including the MC68000-specific read), DBcc, LEA, MOVEA, MOVEQ,
NOP and MOVE to SR. The reset contract comes from section 6.3.1 of
[Motorola's M68000 User's Manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
The public sound ROM/SCSP aperture facts are cited from the
[Model 2 hardware map](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp);
no emulator implementation was copied.

The next sound dependency is documented and independently checked SCSP access
behavior at the observed boundary, followed by more sound-program instructions,
RAM/command transport, interrupts and timed audio. MB86235 geometry still needs
its own independent instruction specification and authentic uploaded program;
this separate Motorola translator supplies no missing geometry semantics.
