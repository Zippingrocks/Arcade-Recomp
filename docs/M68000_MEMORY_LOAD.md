# MC68000 memory loads and absolute-short LEA

Status (2026-10-11): the sound CPU AOT translator now supports byte, word and
long MOVE from `(An)`, `(d16,An)`, absolute-short and absolute-long memory into
Dn, plus absolute-short LEA into An. These are bounded instruction semantics,
not a sound RAM/device implementation or evidence of working audio.

## Specification and boundaries

Implementation is independent of third-party CPU code and follows Motorola's
[M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
printed pages 4-110 (LEA), 4-116–4-118 (MOVE) and 2-18 (absolute-short
addressing). MOVE sets N/Z from the transferred width, clears V/C and preserves
X. Byte and word data-register destinations retain their upper bits. LEA
loads the full effective address and leaves condition codes unchanged. Its
absolute-short address is sign-extended to 32 bits; it is not a memory read.

The translator fixes each operation and operand form in generated native C++.
It reuses the existing strict `read_operand` helper described in
[the CMPI implementation](M68000_CMPI.md), with separate byte/word callbacks,
high-word-first long reads, 24-bit physical data addresses and odd word/long
address refusal. The governing bus references are the
[MC68000 User's Manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf),
sections 2.4/Figure 2-6, 5.1.1 and 6.3.10.

Memory data must come from an implemented bus provider, never assumed RAM.
The load requires a known address register where one is consumed, but no
prior destination value is required to be known. Written Dn bits become
known; upper bits keep their prior values and knownness. MOVE preserves both
the value and knownness of X. LEA defines its complete An destination while
preserving every CCR value/knownness bit, even for odd addresses.

Flags, destination registers, knownness, PC and instruction count are updated
only after a complete successful read. If the second word of a long read is
refused, the first read remains observable and is not rolled back. Diagnostic
fault metadata identifies the rejected transaction. Hardware exception
delivery, prefetch and bus timing are still not implemented.

Updating, indexed and PC-relative MOVE sources, memory-to-memory moves, and
memory-source MOVEA remain outside this extension. LEA forms other than the
existing absolute-long and new absolute-short forms also remain unsupported.
No unknown board-control write or memory region has been enabled.

## Synthetic verification

```sh
python -m unittest discover -s tests -p test_m68k_memory_load_native.py -v
python -m unittest discover -s tests -p 'test_m68k*_native.py' -v
```

The five new tests exercise all accepted size/source/destination-register
fields, truncated extensions, excluded modes, every byte value and word/long
boundary patterns, partial destination knownness, X preservation, physical
address wrap, long-read order and rejected-read observability. They check
unknown address inputs, odd byte versus word/long accesses, and providers
that support bytes but not words. LEA tests cover all address registers,
positive/negative/odd addresses and every CCR value/knownness combination
against a strict bus. An invented load/LEA/compare/branch sequence verifies
instruction composition. The local GCC/UBSan run passed all 22 sound CPU
tests without skips; public fixtures contain no original game bytes.

## Authenticated original-site checks

The local original sound chip `epr-19720.31`, SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`, contains a byte load from
absolute-short `0x00000c04` into D4 at `0x00600188`, followed by an
absolute-short LEA into A0 at `0x0060018c`.

Private GCC/UBSan validation passed **4,096 MOVE state cases and 4,096 LEA
state cases**. All data-register/CCR inputs and the loaded memory byte were
explicitly synthetic. Another 256 synthetic-byte scenarios ran the isolated
block for five completed instructions, stopping at the unsupported CLR.L
postincrement at `0x0060019c`. A strict bus instead refuses the initial byte
read at `0x00000c04`; entering at LEA performs four register-only instructions
before the same unsupported CLR. This is not continuous sound startup.

At the memory-load checkpoint, the original vector-entry static graph discovers **39 sites, 38
translated**, with one unsupported site at `0x0060019c` and no traversal-limit
hit. These supersede the prior CMPI-stage static counts, not any hardware
fidelity estimate. Original bytes and generated original-code validation
artifacts remain private under ignored `build/`.
The subsequent [memory CLR extension](M68000_CLR_MEMORY.md) records the newer
static frontier and isolated clear-loop checks.

The physical sound-board reset sequence, RAM state, unknown `0x00400001`
control write, interrupts and timed SCSP/audio output remain unverified or
unsupported. The existing strict and opt-in reset-vector probe boundaries
are not bypassed. Sound CPU and sound-ROM execution estimates remain about
5%, audio overall about 0%, and original HOTD1 overall about 10%; Gates A/B/C
remain open.
