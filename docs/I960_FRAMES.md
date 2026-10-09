# Intel 80960KB local procedure frames

**Status: initial local CALL/CALLX/RET support passing synthetic native tests; not hardware-verified.**

Original primary reference: [Intel, *80960KB Programmer's Reference Manual*, March 1988, Chapter 4, pp. 4-3 through 4-8](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf). This is **the KB variant** used in Sega Model 2C, not a generic i960 Cx/Jx substitute (their frame alignment may differ).

## Architectural rules corroborated from original Intel documentation

- Each active procedure has 16 local registers (`r0..r15`), while globals (`g0..g15`) retain their values across local calls.
- `g15` is the current frame pointer, **aligned to 64 bytes on 80960KB**. `r0` is PFP, `r1` is SP and `r2` is RIP.
- At a local call, the **caller's** `r2` receives the address after the call; a new local register set is allocated; new FP is the caller SP rounded upward to the next 64-byte boundary; new SP is FP+64; callee `r0` holds the previous FP; IP transfers to target.
- At a local return, the callee PFP supplies the previous FP, previous local registers are restored, and IP becomes the **restored caller's** RIP (`r2`).
- The KB has **four** on-chip local-register sets. Calls beyond cached depth evict the oldest local set to its stack-frame save area. Restoring evicted callers requires memory reloads. Stack save areas need not reflect the newest contents of cached local registers.
- Callee registers other than architectural linkage registers are unpredictable initially. Synthetic runtime clears them to zero only as a deterministic research placeholder; this must not be counted as proven cabinet behavior.
- The low **three** bits of PFP represent return type; bit **3** is prereturn trace. We initially support only ordinary local return type 000 without pending trace, rejecting other forms explicitly.

## Implementation

- `runtime/i960_frame_runtime.hpp`: independent, header-only **native host implementation** of normal local call/return, global FP management and a four-frame spill/reload policy. Not an emulator core.
- `arcaderecomp/i960_cpp.py`: emits direct C++ calls to this runtime for recognized `CALL`, `CALLX`, and `RET` opcodes; all target opcodes are decoded ahead of time.
- `tests/test_i960_frames.py`: compiled synthetic code confirms nested call flow, caller local/global preservation, two evictions across five nested calls and matching restores, missing bus detection, unsupported return type handling and synthetic CALLX transitions.
- `tools/hotd1_boot_probe.cpp`: derives the initial FP from the ROM's PRCB at reset and stops on unsupported instructions/devices. It does **not** implement an accurate Model 2C bus.

## Not implemented or verified

This is not a full 80960KB or Sega Model 2C CPU implementation. **Open**: fault and interrupt frames, `calls`, stack switching, trace controls and transitions, `flushreg` side effects, special registers, all other instructions, correct cycle timing, memory-mapped board I/O, precise frame-cache corner cases (including debugger-visible stale backing save areas), and verification against original arcade execution traces.

We are not calling Gate A or Gate B complete. See `MODEL2C_DEFINITION_OF_DONE.md` for binding proof criteria.

## Authorship policy

The source is independently authored and tested against Intel's published specifications; factual references to external projects do not imply importing their code.
