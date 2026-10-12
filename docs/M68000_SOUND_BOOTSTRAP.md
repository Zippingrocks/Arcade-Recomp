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

- MOVE immediate to SR, restricted to destinations that remain in supervisor
  mode with trace disabled; all interrupt-mask and CCR values are supported,
  while stack-bank changes and trace entry stop before modifying state.
- CLR byte/word/long to data registers; MOVEQ; MOVEA word/long from a data
  register; LEA absolute-long; NOP.
- BRA, Bcc and BSR byte/word displacements; DBcc with a word counter; RTS
  with a bus-supplied return address. See [subroutine semantics and evidence](M68000_SUBROUTINES.md).
  The MC68000 byte displacement `0xff` means -1, rather than the
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
The initial implementation's static traversal found 19 sites: 18 translated
and one unsupported at `0x0060014c`. The MOVE/shift extension described below
finds 30 sites: 29 translated and the next unsupported instruction at
`0x00600174`. These counts are neither sound coverage nor board fidelity.

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

## MOVE and immediate shift/rotate extension (2026-10-11)

The translator now supports MOVE byte/word/long from an immediate or data
register into a data register, and byte/word stores from those sources to
`(d16,An)`, absolute-short and absolute-long destinations. Source values are
captured before destination updates, partial data-register writes preserve
upper bits and their definedness, and absolute-short addresses are
sign-extended. Memory words use a distinct word bus callback: they are not
silently expanded into byte accesses with potentially different device side
effects. Odd word addresses stop before a device callback. Long memory moves,
memory-source MOVE, predecrement/postincrement and indexed forms remain
unsupported.

Immediate LSL/LSR and ROL/ROR support byte, word and long register operands
with counts 1 through 8. Logical shifts update X; rotations preserve its value
and definedness. The native regression uses an independent wide-integer oracle
for all size/register/count/direction/operation fields, all byte operands and
word/long bit patterns, including byte rotation by eight. MOVE tests exercise
aliases, operand masks, immediate extension order, sign-extended destinations,
alignment, bus width and denied-write state.

CLR now requests an explicit `read8_discard` bus transaction. Its default
implementation calls the normal `read8`, preserving the strict fault and
existing read observers. A board provider may override it only when it can
implement the documented transaction and its side effects without producing
unused unknown data. This does not authorize bypassing an unknown device
read. Public tests distinguish ordinary-read refusal from a synthetic
discarded-read transaction and ensure a rejected address prevents the write.

Authenticated original-code metadata identifies the newly supported first
MOVE at `0x0060014c` as a byte write of zero to `0x00400001`. The subsequent
register-only delay loop starts at `0x00600154`; its next device instruction
at `0x0060015e` attempts a word write to `0x00100400`. With explicit synthetic
register inputs (D1 known zero, A5 known `0x00100000`) a private native test
executes **32,771 original instructions** from that isolated loop entry and
then refuses the word write. No device transaction was accepted in this
experiment, and it is not continuous sound startup. The default strict
bootstrap remains at its original 17-instruction SCSP boundary.

These extensions use the same Motorola programmer's manual, printed pages
4-113 through 4-118 (logical shifts and MOVE), 4-160 through 4-162 (rotate),
and 2-18 through 2-19 (absolute and immediate addressing). No third-party CPU
implementation is used. Run all sound CPU regressions with:

```sh
python -m unittest discover -s tests -p 'test_m68k*_native.py' -v
```
