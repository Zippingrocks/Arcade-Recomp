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
