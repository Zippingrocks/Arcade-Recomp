# Sega Model 2C IRQ request/enable register research

**Status: PARTIAL, SYNTHETIC-TESTED, NOT ARCADE-REFERENCE-VERIFIED.**
This is deliberately separate from Intel's 80960KB CPU-internal
interrupt-control register (`0xFF000004`), which governs pin roles.

## CPU-visible Sega board registers

Published Sega Model 2 machine mapping identifies two 32-bit words:

| CPU physical address | Publicly observed function |
| --- | --- |
| `0x00E80000` | Interrupt requests (read); request acknowledgement (write) |
| `0x00E80004` | Current interrupt enable mask (read); queue an enable change (write) |

The public implementation's acknowledgement write **retains** all request
bits that are set in the written value (a bitwise AND). This differs
from write-one-to-clear controllers. It delays enable-mask changes by
approximately **80 ns**, corresponding to **two main CPU cycles at
25 MHz**, rather than making the new mask visible immediately. This is a
**software-observed implementation detail** requiring original PCB or
cabinet evidence before being promoted to arcade-hardware fact.

The public Model 2 device mapping groups active request bits as follows:

| CPU pin | Request source bits | Bit mask |
| --- | --- | --- |
| INT0 / IAC | bit 0 | `0x0001` |
| INT1 | bit 1 | `0x0002` |
| INT2 / INTR | bits 2–9 | `0x03FC` |
| INT3 / INTA | bits 10–11 | `0x0C00` |

This grouping describes **Sega's board-side signals**. Intel's distinct
internal ICR interprets each pin's role based on `0xFF000004` and
determines interrupt vector numbers. Merely finding a request bit does
not amount to delivering a CPU interrupt.

## Independently written, deliberately partial implementation

- `runtime/model2c_irq_registers.hpp` stores request/enable bits,
  bitwise-retain acknowledgements, queued masks and explicit two-cycle
  advancement. A caller must inject a documented IRQ event; **there are
  no automatically fabricated frame/timer/serial events**.
- `runtime/model2c_bus.hpp` exposes the two registers only if
  `enable_partial_irq_registers()` has been called. By default, the
  strict bus still faults on all unimplemented hardware.
- Unknown register addresses and byte/halfword operations fail closed
  rather than emulating an undocumented lane response.
- `tests/test_model2c_irq_registers.py` compiles native C++ from
  **four synthetic tests** for opt-in behavior, reset state, delayed
  enable changes, acknowledgement, pin grouping, replacement of queued
  masks, disabled sources and invalid accesses.
- Synchronous `SYNLD` does **not** falsely claim that interrupt
  registers are ordinary synchronous RAM. Their synchronization and
  fault behavior remain outside that helper's confirmed scope.

### What is NOT implemented

Original event timing, timer countdown at 25 MHz, actual interrupt-line
scheduling, interrupt vector service and priority selection, CPU exception
and return frames, pending event capture when disabled, real Sega I/O
event generation, and all interactions requiring original cabinet traces.
No device currently asserts an actual i960 exception through this class.

**This is research plumbing for future accurate Model 2C interrupts; it
does not make the actual original HOTD1 program boot.**

The strict original `hotdo` native startup still stops after the
documented two 315-5649 serial TX writes at unimplemented serial RX-ready
status. Under *explicitly fictional* serial input it reaches the
second-stage unknown write at `0x00F80000`; neither situation is
bypassed by this IRQ registration work.

## Sources and further work

- [Public Sega Model 2 hardware address map / IRQ observables](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp)
  (historical register observations, **not source code copied into
  ArcadeRecomp**).
- [Intel 80960KB Programmer's Reference Manual, 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf)
  (Chapter 8, CPU vector and pin multiplexing semantics).
- [Independent SYNLD/ICR study](I960_SYNLD_PIN_ROUTING.md).
- [Binding Sega Model 2C completion criteria](MODEL2C_DEFINITION_OF_DONE.md).

Outstanding work is tracked in
[Issue #7](https://github.com/Zippingrocks/Arcade-Recomp/issues/7)
and [Issue #2](https://github.com/Zippingrocks/Arcade-Recomp/issues/2).


## Board-to-Intel IRQ pin observation (synthetic-only, 2026-10-11)

The separate `runtime/model2c_irq_observation.hpp` provides an explicitly
requested **read-only** snapshot joining the existing provisional Sega IRQ
request bit grouping to Intel's independently documented i960KB ICR pin
roles. It observes each pin's currently asserted source-bit mask, role
(direct vector/IAC/INTR/INTA), and configured vector; source bits from a
pin with no direct vector **remain unresolved** rather than being silently
mapped to an arbitrary interrupt. A direct configured vector is only a
*candidate*, not an interrupt the CPU has accepted.

The observation has **no priority winner, pending event scheduler, IRQ
entry, supervisor stack, interrupt return, cycle accounting, IRQ ACK or
device side effect**. There is deliberately no API returning a selected
vector or writing into the CPU. Board IRQ registers and injected events
remain explicitly synthetic/opt-in, and the board's request-enable latency
requires an externally advanced scheduler. This infrastructure must not
be confused with original Model 2C IRQ acceptance or Intel fault frames.

`tests/test_model2c_irq_observation_native.py` compiles with GCC and
Clang UndefinedBehaviorSanitizer and tests the KB reset multiplexing
rules, original HOTD1 ICR `0x0F0E0D0C`, explicit queued enable changes,
ACK source grouping, 4096 possible synthetic 12-bit request combinations,
and state immutability. All tests use invented request injections with no
actual arcade trace. Original board IRQ timing, priority, line-level and
entry/return proof remains missing; Issue #7 stays open.


## Intel KB vector priority classification (2026-10-11)

`runtime/i960_interrupt_priority.hpp` now implements an independently
written, **pure priority review**, grounded in the [Intel 80960KB Programmer's
Reference Manual, Chapter 8 pp. 8-2, 8-3 and
8-9](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf).
For a valid 8-bit interrupt vector, Intel defines a priority level equal to
integer `vector / 8`. Vectors 0–7 are unavailable and vectors 244–251
are reserved. A priority-31 vector is always eligible for immediate
service; other vectors with a priority **equal to or below** the
processor's current priority would be posted pending instead of serviced
immediately. The pure helper also provides the documented *byte offsets
and bit positions* in Intel's pending-interrupt table and the offset of
the handler entry, **without touching any CPU memory**.

The existing `model2c_irq_observation.hpp` adds an *optional read-only
second pass*, `review_model2c_irq_priorities(snapshot, current_priority)`.
**The caller MUST supply a known or hypothetical current priority (0–31).**
The project does not silently interpret an unverified `process_controls`
field, because actual Intel control-state tracking and interrupt-frame
entry/return are incomplete. Non-vector IAC/INTR/INTA pins and unsupported
vectors remain explicitly unclassified or invalid. Multiple candidates
are never arbitrated by this helper, and no pending interrupts are
posted, acknowledged, serviced or delivered.

Synthetic GCC/Clang UBSan tests cover all **8,192 combinations** of
256 vectors and 32 program priorities, Intel table offsets, the
priority-31 special case, the original `hotdo` ICR `0x0F0E0D0C`
(vectors 12–15, all priority 1), reset multiplexing and reserved-vector
rejection. This advances documented CPU *priority research* and tests,
but **does not establish actual Model 2C interrupt acceptance, timing,
priority-state accuracy, supervisor frames or original-cabinet behavior**.


## Proven-known CPU priority after partial IAC 0x93 (2026-10-11)

The native `CPU` now carries a **knowledge marker and committed source
value** for Intel process controls. `frame_init` invalidates the marker:
a default-constructed CPU has `process_controls=0` as a host convenience,
**not an established Intel priority of zero**.

Only *successful, explicitly enabled and validated* IAC 0x93
reinitialization records the documented `process_controls=0x001F2002`
(initial program priority 31) as known. Failure to validate the PRCB or
frame leaves priority unknown; the default strict original-ROM path
still refuses unsupported reinitialization. The new
`kb_known_cpu_program_priority(cpu)` refuses unverified state or a CPU
process-controls word that differs from the last committed source value.
`review_model2c_irq_known_cpu_priority` integrates this guard with the
existing board IRQ snapshot, returning **no review** when the priority
is unknown. No direct priority write, `MODPC` instruction, IRQ
arbitration, pending-table mutation, interrupt service or supervisor
frame is implemented.

After opt-in IAC 0x93, the documented original HOTD1 ICR vectors
12–15 are **priority 1** and would be pending at program priority 31.
This is an *architectural research inference conditional on our partial
reinitialization model*, not an observed HOTD1 board interrupt or proof
of any original handler execution. The synthetic GCC/Clang test checks
failed and successful IAC validation, lack of false default knowledge,
manual PC changes, frame initialization invalidation and read-only IRQ
review. Future `MODPC` and fault-return implementations must explicitly
update or invalidate the knowledge marker. A direct external rewrite
that restores the exact same process-controls bits is not independently
observable by this helper, so it must not serve as a security boundary.


## Native MODPC (655h) — strictly bounded, fail-closed (2026-10-11)

The original **Intel 80960KB Programmer's Reference Manual** (March 1988),
Chapter 11 pp. 11-82–11-83, specifies MODPC operands as dummy
source / mask / source-and-destination. With mask zero, MODPC copies
process controls to the destination even in user mode. With a nonzero mask,
the processor must be in supervisor mode, changes only masked bits and
returns the **previous** process controls through the destination.
**Reducing** program priority also requires an interrupt-table pending
check before execution can safely resume.

The independent i960 REG decoder and C++ AOT translator now recognize
**opcode 655h**. The native `kb_modpc_checked` handler requires already
established PC provenance from the opt-in IAC `0x93` path. It implements
the **mask-zero read** and **supervisor-mode, priority-field-only
nondecreasing update** (including idempotent writes), preserving the prior
PC value as the destination. The mask and proposed replacement are
captured before the destination is overwritten, so register aliases are
safe.

Cases requiring absent hardware/CPU behavior deliberately stop with
specific diagnostic codes and **no PC/register mutation**: unknown
process-controls origin, user-mode nonzero mask (architected TYPE.MISMATCH
fault not yet implemented), masks touching non-priority fields such as
trace/state/resume/mode/reserved bits, and any priority *lowering*
(which requires pending-interrupt table examination). The translator also
rejects undocumented special-register encoding modes. The source1
operand is Intel's unused dummy; actual mask comes from source2.

GCC and Clang UBSan ROM-free tests cover decoding/AOT, 32 synthetic
priority levels and nondecreasing transitions, aliasing, mask-zero reads,
stale state, user privilege, unsupported fields, and rejection of a
priority-lowering MODPC after a successfully modeled IAC `0x93`.
This does **not** implement Intel fault entry, pending-table scanning,
priority arbitration, MODPC trace delay, interrupt delivery or
original Model 2C board behavior. Strict original HOTD1 boot remains
blocked by real Sega 315-5649 RX/status evidence.

Primary reference:
https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf


## Static pending-interrupt record validation (2026-10-11)

Intel's 80960KB March 1988 manual, Chapter 8 pp. 8-2–8-3 and 8-8–8-9,
defines the interrupt table's first **36 bytes**: little-endian 32-bit
pending-priority mask at offsets 0–3, followed by 32 vector bytes at
offsets 4–35. Vectors 0–7 are unusable and 244–251 reserved. When more
than one vector has the same priority, the KB chooses the **highest vector
number** first. The CPU's actual posting/inspection of the table uses an
**atomic, bus-locking read/write transaction**.

The independent `runtime/i960_pending_interrupt_snapshot.hpp` now
validates a **caller-supplied immutable snapshot**, checks that its
priority bitmap equals the priorities represented in the pending-vector
bits, rejects reserved vectors, and calculates only the *highest
potentially serviceable vector* for an **explicit current priority**.
Priority-31 pending vectors are treated as potentially serviceable even
when the caller supplies program priority 31. There is no silent
assumption that the table is empty.

Crucially, this helper is **not integrated with CPU interrupt delivery
or MODPC priority lowering**. It cannot validate atomic capture
coherence, read the actual PRCB's interrupt table, lock a bus, mutate
pending bits, ACK a board line, schedule an interrupt, or enter an Intel
handler. A returned candidate is not a real hardware interrupt.
`kb_modpc_checked` still halts on *all* priority reductions, even when
an invented snapshot is empty. Synthetic GCC/Clang UBSan tests cover
all 256 vectors against 32 priorities (8,192 cases), mixed priorities,
same-priority ordering, inconsistent bitmap data, reserved vectors,
read-only state preservation and the unchanged fail-closed MODPC guard.

Reference: Intel 80960KB Programmer's Reference Manual (1988),
https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf

## Optional locked pending-table capture contract (2026-10-11)

The native `Bus` now exposes optional `read_pending_record_locked`
for one coherent/exclusive 36-byte Intel pending-table snapshot. There is
**no implementation** of this callback in the current Model 2C StrictBus.
Ordinary `read32` is deliberately **not** a fallback, since Intel KB
pending-interrupt checks require an atomic read/modify/write transaction
under a table lock. A callback returning true is the provider's assertion
of locking, **not independent hardware proof**.

`runtime/i960_pending_interrupt_acquisition.hpp` requires proven CPU
priority, an aligned nonwrapping PRCB interrupt-table address, a registered
provider and a complete well-formed vector/priority record. Missing or
declined providers and corrupt records refuse without exposing candidates
or raw table bytes. Read-only results are always labeled
`provider_asserted_unverified`. No pending-table modification, bus LOCK
waveform, Intel interrupt entry/return, vector delivery or `MODPC`
priority lowering is implemented. The default original-game boot path
and all Model 2C completion gates remain unchanged.

Synthetic GCC/Clang UBSan tests cover missing/failed provider, poisoned
partial buffers, invalid CPU/address, reserved and inconsistent records,
and successful synthetic observation without delivery. This is software
interface groundwork, not original-cabinet evidence.

Intel 80960KB manual Ch. 8 pp. 8-8–8-9:
https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf


## Read-only draft pending bitmap posting/removal (2026-10-11)

The independent i960_pending_interrupt_record_edit.hpp builds a
**pure, uncommitted** draft of the Intel 80960KB's 36-byte pending
interrupt bitmap after posting a valid vector or removing the highest
eligible pending vector. It maintains paired priority and vector bits,
is idempotent on duplicate posting, respects highest-vector tie order,
and clears a priority bit only after its final pending vector is gone.

All inputs are checked against the existing Intel record validator
before any edited bytes or candidate metadata are returned. Invalid
records or reserved vectors are refused with zero candidate and zero
output. Neither operation modifies original input RAM or CPU state.

This is **NOT a real Intel locked table transaction**: there is no
bus-lock capture, atomic commit, CPU supervisor entry/return, IRQ ACK,
priority lowering or connection to the default Sega Model 2C StrictBus.
Ordinary writes of these returned bytes would be wrong and must not
be used. ROM-free GCC/Clang UBSan tests cover 256 vectors x 32
priorities, every valid same-priority vector pair, a full 240-vector
drain, malformed source records, duplicates and state immutability.
Project hardware-fidelity estimates remain unchanged.

Primary Intel manual (Mar 1988), Chapter 8:
https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf
