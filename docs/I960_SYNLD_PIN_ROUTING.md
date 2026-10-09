# Intel 80960KB SYNLD and interrupt-pin routing

**Project status:** CPU instruction-level tests passing; no original-cabinet
interrupt delivery or complete Sega Model 2C implementation.

## Authoritative instruction semantics

The [Intel 80960KB Programmer's Reference Manual (March 1988)](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
**Chapter 11, p. 11-124**, defines \`synld src,dst\` (REG-format extended opcode
\`0x615\`). The CPU reads one aligned word **from memory pointed to by src**
into the destination register, and waits for prior memory accesses to
finish. On success, \`AC.cc=010\`; on documented synchronous *Bad Access*,
\`AC.cc=000\` without an ordinary bad-access CPU fault. In the bad-access
case the destination register is not overwritten by unverified data.

At the special CPU-internal address \`0xFF000004\`, \`SYNLD\` accesses the
80960KB Interrupt Control Register (ICR). This is the reverse direction
of the already supported \`SYNMOV\` operation used by original HOTD1 code.
**Note:** some Intel high-level summaries use confusing wording about the
direction of \`SYNLD\`. The primary detailed instruction definition is
unambiguous: source **memory** -> destination **register**.

### What ArcadeRecomp implements

- \`arcaderecomp/i960.py\`: independent decoder identifies \`0x615\`.
- \`arcaderecomp/i960_cpp.py\`: ahead-of-time host C++ lowering; no
  guest-i960 instruction decoding required during native execution.
- \`runtime/i960_sync_runtime.hpp\`: reads the internal ICR directly,
  or requires an **explicit synchronous-read completion callback**.
  A failed callback sets CC=000 and leaves the destination unchanged.
  Without a synchronous callback, execution stops safely; an asynchronous
  \`read32\` may never substitute for a synchronous peripheral read.
- \`runtime/model2c_bus.hpp\`: synchronous reads succeed for backed
  i960 program ROM, game-data ROM or work RAM only. Unmapped addresses,
  Sega serial I/O, and CPU wait-state registers return Bad Access;
  no made-up peripheral values or Model 2C timing are introduced.

**Limitation:** completion of a plain RAM/ROM read is functional
modeling, not independently timed Model 2C memory-bus equivalence.

## CPU interrupt-control pin routing

Intel's manual, **Chapter 8 pp. 8-10 to 8-11**, assigns four independent
8-bit vector fields in the 32-bit ICR:

| Pin | Field in 32-bit ICR | Special meaning |
| --- | --- | --- |
| INT0 | bits 7:0 | Vector 0 selects external-IAC input mode |
| INT1 | bits 15:8 | Direct interrupt-vector field |
| INT2 | bits 23:16 | Vector 0 selects external INTR mode |
| INT3 | bits 31:24 | Becomes INTA if INT2 selects external INTR |

At the Intel documented reset ICR of \`0xFF000000\`, the effective
configuration is **INT0=IAC, INT1=direct vector field 0, INT2=INTR,
INT3=INTA**. The original \`hotdo\` program uses compiled \`SYNMOV\` to
install \`0x0F0E0D0C\`. The resulting four direct vectors are
**INT0=12, INT1=13, INT2=14, INT3=15**.

\`runtime/i960_interrupt_pins.hpp\` is an original, pure,
side-effect-free translation of those publicly documented rules.
It does **not** assert an interrupt, schedule cycles, acknowledge
external controllers, enter a supervisor stack, or execute a return.

\`tests/test_i960_synld_routing.py\` compiles native C++ with **five
synthetic tests** for SYNLD, forced alignment, ICR readback,
plain-memory completion, bad-access CC, refusal of fake asynchronous
completion, reset multiplexing and all four original ICR vector fields.

## Sega board status and safety boundary

The original HOTD1 second-stage instruction at \`0x000006D4\` has
already been isolated and verified to write ICR \`0x0F0E0D0C\`.
This module is a verified **CPU mechanism**, not proof that the original
program has passed the earlier unmapped **\`0x00F80000\`** board write.

That hardware address remains undocumented; the bus must not invent
a watchdog or ignore the write. Likewise, genuine 315-5649 serial
receive status and timing have not been reconstructed.

**Model 2C is NOT COMPLETE.** Next actual gates: evidence-based board
decoding for \`0x00F80000\`; CPU interrupt entry/return/priority
semantics; original-arcade serial timing and graphics/audio runtime.
