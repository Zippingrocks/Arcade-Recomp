# Intel KB arithmetic controls and native MODAC

Primary reference: [Intel 80960KB Programmer's Reference Manual, March
1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf),
pp. 3-7 through 3-11 and 11-79.

MODAC (`645h`) takes a mask, replacement value and destination. It modifies
selected arithmetic-control bits and returns the previous complete AC word.
Both sources permit integer literals. Reset and reinitialization leave AC
undefined. Reserved AC bits must be zero. The documented fields occupy
mask `0xFF1F917F`: condition code, arithmetic status, integer overflow
flag/mask, precise-fault control, FP flags/masks, normalization and rounding.

`runtime/i960_arithmetic_controls.hpp` provides the canonical AC snapshot
accessor. It combines the existing live condition code and integer
overflow fields with storage/knownness for the remaining bits. Therefore
native comparisons, synchronous operations and masked integer overflow
remain visible to the next MODAC. Successful MODAC updates the same live
fields. The remaining fields are stored, not newly implemented behaviors.

`kb_establish_arithmetic_controls` explicitly imports a verified saved word
or synthetic fixture. It never runs automatically at reset. MODAC requires
all previous bits to be known because its destination receives the entire
old word. Even a full overwrite refuses unknown previous state; the runtime
does not yet track undefined general-register values. Reserved-one states,
unsupported register modes and an outstanding overflow also refuse.
Refused execution does not change AC, destination or instruction pointer.

The ROM-free native tests cover individual bits, randomized masks, literals,
every source/destination alias, reserved/unknown states, a translated
MODAC/ADDI/CMPO sequence, FP control preservation through exact and refused
operations, stale-state prevention and reset/IAC invalidation.
They use GCC/Clang with undefined-behavior checks when available.

This is synthetic instruction evidence, not an original-ROM instruction-site
or cabinet trace. Guest AC initialization from undefined reset, FP rounding,
fault dispatch, interrupt entry/return and board timing remain open.
CPU faults stay estimated at 15%, CPU 55%, Model 2C 20%, and original
HOTD1 overall 10%; Gates A/B/C remain open.
