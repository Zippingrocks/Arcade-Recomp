# Intel i960KB SYNMOVQ and the original HOTD1 reinitialize IAC

**Project status: independent native translation / isolated original-ROM test passed.
Processor reinitialization is NOT implemented. Sega Model 2C is NOT complete.**

## The instruction is not a generic memory copy

The **primary, original Intel 80960KB Programmer's Reference Manual (March 1988)**
documents `SYNMOVQ` at Chapter 11, pages **11-126–11-128**:

- Operand 1 is a **destination address stored in a register**; operand 2 is
  a **source address stored in a register**.
- It synchronously transfers **four 32-bit words** from memory to memory,
  forces quad-word (16-byte) alignment, and waits for pending memory
  transactions to complete.
- A successful ordinary synchronous transfer sets arithmetic condition
  code `AC.cc` to binary `010`; bad access can report `000`.
- **Destination `0xFF000010` is the local processor IAC endpoint.** A
  four-word message is delivered to the CPU, not written into generic RAM.

The same **Intel KB manual**, Chapter 13, page **13-10**, identifies message
type **`0x93`** as **Reinitialize Processor**. Its four words are:
`0x93xxxxxx` (type and unused fields), the System Address Table address,
the new Processor Control Block address, and the next start instruction IP.

Primary documentation (original Intel text):
https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf

Intel's separate i960 Assembler User's Guide also shows a near-identical
IAC transfer with the `0xFF000010` destination:
https://datasheets.chipdb.org/Intel/80960/manuals/48527606.PDF

## Original `hotdo` arcade startup evidence

Independent disassembly of the user's **hash-verified original `hotdo` ROM**
finds this startup sequence. The sequence exists in the original program
regardless of how the serial controller behaves:

| Original ROM address | Instruction / message component |
| --- | --- |
| `0x00000690` | Prepare destination `0xFF000010` in `g0` |
| `0x00000698` | Prepare source pointer `0x00000560` in `g1` |
| `0x000006A0` | `synmovq g0,g1` — submit processor IAC |
| `0x00000560` | Message `0x93000000` |
| `0x00000564` | New SAT `0x00000000` |
| `0x00000568` | New PRCB `0x00510E00` |
| `0x0000056C` | New start instruction IP `0x000006B0` |

This is a **processor reinitialization request**. The game previously
copied its PRCB and initialization state into working RAM; the IAC
repoints the CPU at the new control block and new startup code.

## Independent implementation

- `runtime/i960_sync_runtime.hpp`: newly authored, explicit
  `sync_move_quad` instruction helper with four-word source reads,
  16-byte address alignment, typed internal-IAC detection and a complete
  pending-message record. It **halts deliberately** on an unimplemented
  hardware-synchronous ordinary destination or an unimplemented IAC type.
- `runtime/i960_frame_runtime.hpp`: records a pending message and
  informative stop codes; no fabricated reinitialize or reset occurred.
- `arcaderecomp/i960_cpp.py`: ahead-of-time lowers `SYNMOVQ` to a native
  C++ operation. It does **not** interpret i960 instruction opcodes while
  the host binary executes.
- `tests/test_i960_sync.py`: four compiled artificial-instruction tests
  cover valid `0x93`, forced quad alignment, unsupported IAC, unsupported
  ordinary synchronous writes, a missing bus and an unmapped source.
- `tools/hotd1_iac_probe.cpp`: user-local native executable to inspect
  exactly **one original ROM instruction** at `0x6A0` with the register
  inputs reconstructed from static disassembly. This is NOT a real startup
  traversal or evidence that the program passed its serial handshake.

### Private local original-ROM test

The original reconstructed `maincpu` (2 MiB; **not committed**) was
compiled and run with a private test harness. At the isolated `0x6A0`
instruction, it produced:

```text
ISOLATED ORIGINAL I960 INSTRUCTION, NOT AN ARCADE BOOT
pending_message=0x93000000 sat=0x0 prcb=0x510e00 requested_next_ip=0x6b0
```

Separately, with an **explicitly synthetic** receive/status input fixture
(artificial serial bytes and artificial status delays), the original ROM's
compiled code reached `0x6A0` after **91,116 dynamic native instruction
steps** and captured the same message. This is **not an arcade timing
measurement**, does **not** establish authentic serial protocol replies,
and must not be counted as a genuine uninterrupted arcade boot.

Without the fixture, the strict original-ROM run still stops correctly
at `0x000A372C` waiting for an unimplemented real serial-status source,
following the original two TX bytes (the earlier 1,910-step verified trace).

## Reproduce the isolated IAC check locally

Using only your own legally obtained original arcade dump:

```bash
python -m unittest discover -s tests -v
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --output build/hotd1/hotd1_i960.cpp --limit 8192
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_iac_probe.cpp -o build/hotd1/iac_probe
build/hotd1/iac_probe build/hotd1/maincpu.bin
```

**No ROM bytes, ROM-derived C++, game assets, or executables** are shipped
through GitHub or source-only CI artifacts.

## Current code coverage boundary

After this addition, **130/130 unique instruction addresses in the
currently recovered early startup CFG emit native code**. This number is
**not** a measure of full-game, CPU, coprocessor or Model 2C completion.
`SYNMOVQ` is recognized and its four-word IAC data is captured, but
**the requested processor reinitialization is still intentionally
unimplemented**. The i960 control-state reset, interrupt stack, PRCB
effects, faults, and following stage remain future work.

A complete Model 2C implementation requires independently validated
interrupt and lightgun hardware, processor control semantics, graphics,
audio, actual arcade timing, and faithful all-chapters playthroughs.

See `docs/MODEL2C_DEFINITION_OF_DONE.md` and Issue #5.
