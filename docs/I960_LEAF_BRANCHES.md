# Intel 80960KB leaf branches — BAL, BALX and BX

**Status: SYNTHETIC TESTED ONLY. Model 2C is NOT complete.**

## Why these operations matter

The i960 has two distinct control-flow mechanisms. `CALL`/`CALLX` and
`RET` use local register-frame transitions; leaf procedures can instead
use **branch-and-link** without creating a new frame. Confusing these
mechanisms changes stack/register state and can silently corrupt the game.

The March 1988 **Intel 80960KB Programmer's Reference Manual** (instruction
reference, *bal, balx*, p. 11-17) defines these transitions:

| Instruction | Native effect |
| --- | --- |
| `BAL` | `g14 = current_ip + 4; ip = relative_target` |
| `BALX` | `destination_register = current_ip + instruction_length; ip = effective_address` |
| `BX` | `ip = effective_address`; no link register write |

These branches do not call `frame_call` or allocate local-register windows.
For extended targets, the destination IP is word-aligned by the processor.
`BALX` resolves its target **before** changing the link register, even
when the same general register supplies the target address.

Unlike a load, `BX`/`BALX` operate directly on a computed effective
address. They must not read an address *from* the bus at that address.

## Code and proof

- `arcaderecomp/i960_cpp.py` compiles the three decoded instruction
  operations directly into native C++. The game opcode is not decoded at
  runtime.
- `tests/test_i960_leaf_branches.py` has three ROM-free native integration
  tests: direct BAL to BX return without a frame; BALX with matching
  target/link register and low IP-bit masking; and 8-byte MEMB BALX
  preserving the correct return IP.
- GitHub Actions completed **69 synthetic tests successfully** on
  feature commit `e98d5bd3b14a4d4b5f195e085282d4de25b11937`.
  [Workflow evidence](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37902661193).

## Remaining discovery boundary

Indirect `BX`/`BALX` destinations cannot, in general, be inferred from
the instruction's static encoding. The recompiler still halts at a target
without generated code; it does **not** interpret new instructions at
runtime. A known, independently verified target can be supplied through
`--extra-entry` for additional ahead-of-time translation, but dynamic
target discovery remains future work.

This tranche proves synthetic CPU instruction semantics, **not**
original-`hotdo` execution through these instructions, actual arcade
I/O, asynchronous interrupts, full boot, graphics or gameplay.

## References

- [Intel 80960KB Programmer's Reference Manual, March 1988, Chapter 11](https://www.bitsavers.org/components/intel/i960/80960KB_Programmers_Reference_Manual_Mar88.pdf).
- [Mark Smotherman, i960 subroutine mechanisms](https://mark.people.clemson.edu/subroutines/i960.html).
- [Binding Model 2C definition of done](MODEL2C_DEFINITION_OF_DONE.md).
