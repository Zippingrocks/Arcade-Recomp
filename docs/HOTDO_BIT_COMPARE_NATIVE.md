# Original HOTD1: bit, condition and compare-increment lowering

Date: 2026-10-09. Baseline: `46bf7c757865a6bf0f8c463cf36ae61e3d097b34`.

**Model 2C is NOT complete. This is tested CPU instruction work, not an
arcade boot or a solution to the two outstanding authentic hardware gates.**

## Delivered

`arcaderecomp/i960_cpp.py` now lowers NOT, ANDNOT, CHKBIT, BBC/BBS, all eight
TEST condition forms, and CMPINCI/CMPINCO. Existing compare-decrement
handling shares the operand-snapshot implementation and is regression-tested.
No runtime device, memory-map or serial-response implementation was changed.

Functional rules were checked against Intel's original [80960KB Programmer's
Reference Manual, March 1988, archived full text](https://archive.org/stream/bitsavers_inteli9608ferenceManualMar88_20413561/80960KB_Programmers_Reference_Manual_Mar88_djvu.txt):
ANDNOT (11-11), BBC/BBS (11-20), CHKBIT (11-31), CMPINC (11-37), NOT
(11-94), TEST (11-131/132), and COBR encoding (Appendix B-4).

In particular, ANDNOT uses src2 AND NOT src1. Compare-increment compares
both original operands before storing src2+1; signed overflow of that
increment is ignored. Bit selection uses position modulo 32 and replaces
the condition code with 000 or 010. TEST preserves the condition code and
ignores its m1 field. Existing undefined-condition diagnostics are retained.
Unsupported special-register encodings remain deliberate stops; this is
not a claim that all encodings, tracing, exceptions or CPU timing work.

## Measured coverage change

The same original image and two roots, `0x000005F0` and `0x000006B0`, were
used before and after the change. Discovery was not broadened to inflate
coverage, and unsupported instructions were not replaced by no-ops.

| Measure | Baseline | This pass |
| --- | ---: | ---: |
| Static candidate locations | 3,051 | 3,051 |
| Native-emitting locations | 3,025 | 3,042 |
| Deliberately unsupported locations | 26 | 9 |
| Full automated suite | 127 passing | 137 passing |

The 17 newly supported original sites comprise three NOT, two ANDNOT, two
CHKBIT, five BBC, one BBS, one TESTNE and three CMPINCO sites. CMPINCI and
the other TEST conditions are covered by synthetic instruction tests.
These are selected static candidates, not a percentage of the game or
proof that all possible gameplay paths have been found.

The nine remaining stop sites include three currently unsupported signed
arithmetic instructions and six candidates the current decoder does not
recognize. Neither all six words being executable code nor the entire CPU
being nine instructions away from completion is established.

## Executed validation

The downloaded baseline source ZIP matched GitHub Actions artifact SHA-256
`e1827ac914ca0b8298f20c4c58a969812fd49afec265655409094c873898d9a3`.
All 29 original ROM chips passed the manifest's size/CRC32/SHA-1 checks.
The rebuilt 2 MiB main-CPU image has SHA-256
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

Ten new native tests in `tests/test_i960_bit_compare_native.py` exercise
**54,978 synthetic case rows per compiler**, using GCC 14.2 and Clang 17,
with UndefinedBehaviorSanitizer and non-recovering diagnostics. Each case
checks all 32 registers, next IP, condition-code value/definedness, and stop
metadata. The Python expected-state oracle does not call the decoder or
emitter. It separately calculates signed comparisons, per-bit ANDNOT,
modulo-position selection and explicit TEST truth sets.

The cases cover literals, local/global registers, source/destination
aliasing, word-boundary values, arithmetic wrap, forward/backward/self
branches, both branch outcomes, prediction hints, ignored fields,
undefined conditions, and unsupported special encodings. Case rows are
not claimed to be unique hardware states or a statistical confidence level.
The full suite actually completed **137 tests, all passing**.

`tools/experimental/hotdo_bit_compare_probe.py` then compiled the actual
original-program translations and checked the 17 selected locations with
**2,912 synthetic-state cases per compiler**, again with GCC and Clang and
UBSan. Both passed with no diagnostics. This is isolated single-step
validation, not continuous game execution. Its [metadata report](reports/hotdo_bit_compare_native.json)
contains addresses, hashes, counts and boundaries, not ROM instructions
or generated game code. The CLI also refused an incorrect image hash and
an attempt to overwrite its own input with a report.

Finally, the complete original startup translation was rebuilt and run:

| Strict mode | Successful steps | Deliberate hardware stop |
| --- | ---: | --- |
| Default | 1,904 | IP 0x000A375C, write 0x01C00014 |
| Documented TX enabled | 1,910 | IP 0x000A372C, read 0x01C0001A |

Both produced diagnostic exit 3, as expected. TX-enabled output recorded
channel 2 FF, then channel 1 01. No receive-ready bytes or speculative
serial replies were injected. **The authentic-input startup boundary has
not moved.**

## Reproduce

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python tools/experimental/hotdo_bit_compare_probe.py --image build/hotd1/maincpu.bin --output build/hotd1/bit-compare.json --cxx g++ --cxx clang++
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 --output build/hotd1/hotd1_i960.cpp
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000
build/hotd1/strict_probe build/hotd1/maincpu.bin 10000 --serial-tx
```

The last two commands intentionally return exit 3. The isolated verifier
requires the repository's `tests` directory; its generated game code and
executables are temporary and are removed. All source ROMs, reconstructed
images and full-game translation output must remain private.

## Remaining gates

Issue #4 still requires authentic Sega 315-5649 receive/status behavior,
endpoint responses and timing. Issue #6 still requires identifying the
physical meaning of `0x00F80000`. Neither is solved by this CPU change.
Interrupt delivery, complete CPU faults/timing, geometry, graphics, sound
and full original-game validation also remain incomplete. See the binding
[Model 2C definition of done](MODEL2C_DEFINITION_OF_DONE.md).
