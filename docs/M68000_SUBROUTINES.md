# Native MC68000 subroutine calls and returns

Date: 2026-10-11. Scope: BSR short/word and RTS, ahead-of-time translated
from fixed instructions. No interpreter, host-language call stack, sound RAM
provider or fabricated board response is introduced.

## Primary sources and the stack word order

Motorola's [M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PM.pdf),
printed 4-59/60 and 4-169, specifies the BSR displacement relative to PC+2,
the pushed next-instruction address, the four-byte stack adjustment and RTS's
stack-supplied return PC. Neither instruction changes the condition codes.
Only MC68000 short/word encodings are enabled: a low byte of zero introduces
one extension word; `0xff` remains signed -1, not a 68020 long displacement.

The architectural manual alone does not establish the two-word bus order.
Motorola's [US4325121 patent](https://patents.google.com/patent/US4325121A/en)
([original scanned PDF](https://patentimages.storage.googleapis.com/1d/56/27/99bd3a344f0271/US4325121.pdf))
provides the primary microcode diagrams:

- PDF page 77, printed columns 49-50, Appendix B: ATH is the temporary
  address register's upper 16 bits; DOB/AOB drive external data/address buses.
- PDF page 149, printed columns 193-194, Sheet E rows E-G, columns 3-4:
  `bsri2`/`bsrw2` write ATH at SP-4, then `bsri3`/`bsrw3` write the low
  portion at SP-2. Thus BSR writes **high word, then low word**. It must not
  inherit the different ordering of MOVE.L predecrement or CLR.L.
- PDF page 158, printed columns 211-212, Sheet E column 7, rows M/N/P:
  RTS reads at SP and SP+2, retaining the first word as ATH before assembling
  the return PC. Reads are likewise **high word, then low word**.

These scanned diagrams and their abbreviations were visually inspected.
The patent describes an early processor design, not a Model 2C capture;
the implementation claims instruction/data-transaction semantics, not exact
prefetch timing, address-error sequencing or cabinet validation. No
third-party CPU implementation was copied.

## Runtime boundaries

A7 must be known before any stack transaction. Stack arithmetic wraps at
32 bits, while each physical bus address is independently masked to 24 bits.
Each long transfer uses two explicit word callbacks; byte-only providers do
not accidentally satisfy word accesses. Odd stack addresses stop before a
callback. Successful calls/returns preserve all other registers and SR value
and knownness, including unknown condition-code bits.

On a refused transaction, architectural CPU data is retained diagnostically;
already accepted bus writes or read side effects are not rolled back. The
stop is latched, so calling `step` again cannot silently retry it. This is not
the real MC68000 BERR microstate or an exception frame. Restoring a diagnostic
checkpoint requires restoring the CPU and any affected bus state together.

BSR discovery follows both the callee and the possible return continuation.
RTS ends static discovery at its site. Execution reads the actual return
address from the supplied bus, with no remembered or guessed caller. As with
existing branches, odd or undiscovered destinations are diagnosed on the
next step after the transfer. Instruction prefetch, trace, interrupts,
stack-bank switching, RTD/RTE/RTR, JSR and exception delivery remain outside
this subset. Existing supervisor/trace/interrupt-mask guards are unchanged.

## Verification and original-byte evidence

Six ROM-free tests in `tests/test_m68k_subroutine_native.py` cover every
short and word displacement, truncations, PC wrapping, recursive/shared
targets, nested calls, dynamic returns, every CCR value/knownness pair,
stack/bus wrapping, every refused word cycle, partial effects, alignment,
unknown A7, word-only access and control-state guards. Focused GCC/UBSan
execution and strict Clang 19 syntax checks pass; the latter is not Clang
runtime execution. An independent code review found no actionable issue.

The original sound chip authenticates against size, CRC32 and SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`. Its BSR.W at `0x6001BE`
pushes return address `0x6001C2` and branches to `0x600352`. The original
site passes 3,072 isolated native checks with supplied CPU state and an
explicitly synthetic stack. Starting there executes four instructions before
the next unsupported site at `0x60035E`. A strict no-memory provider instead
refuses the first word write at `0x1FFC`, with zero completed instructions.
This does not bypass any earlier board access or install sound RAM.

The startup graph grows from 48/47 discovered/translated sites to 88/77,
revealing eleven unsupported sites through call targets and continuations.
This is useful code discovery, not measured boot or sound coverage.
Continuous sound probes remain unchanged: 17 instructions before the strict
SCSP read at `0x100401`, or 18 with the optional documented SCSP-control
subset before refusing the board write at `0x400001`. Main-CPU serial RX/status
is still unobserved. No physical hardware response or audio output is claimed.

Sound CPU estimate remains 5% -> 5%, audio 0% -> 0%, overall original HOTD1
10% -> 10%. Gates A/B/C remain open.
