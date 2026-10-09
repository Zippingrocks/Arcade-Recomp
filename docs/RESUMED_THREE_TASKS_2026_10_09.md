# Resumed three-task pass — 2026-10-09

**Model 2C is NOT complete. The three requested tasks are NOT all finished.**
This pass delivers a tested CPU-instruction expansion and records the two unresolved hardware questions without fabricating behavior.

## 1. i960 transfer and shift work delivered

New native AOT operations: LDL/LDT/LDQ, STL/STT/STQ, register forms of MOVL/MOVT/MOVQ, SHRI, and SHRDI. Existing SHLO/SHRO implementations had an actual correctness bug: masking the shift count with 31 made counts of 32 and larger wrap. Intel specifies zero for those large ordinal shifts; the implementation now honors that. SHRI sign-fills, while SHRDI rounds division toward zero. Counts are handled without undefined C++ shifts or implementation-defined signed conversions.

Group transfers validate register-group alignment, capture the effective address before overwriting an aliasing destination, preserve little-endian word order, and validate the entire ordinary-memory span before modifying registers or RAM. New explicit block callbacks refuse unmodeled MMIO; they never silently translate a device burst into unrelated single-word transactions. Invalid/overlapping register groups are not assigned invented semantics.

**Scope limitations:** multiword memory is currently supported only at four-byte-aligned addresses in backed normal memory. Unaligned fault policy, multiword MMIO/burst timing, and literal MOVL/MOVT/MOVQ forms remain unsupported. Integer-overflow/fault handling and complete instruction-set coverage remain future work. The callback refusal is a diagnostic stop, not a claim about original hardware Bad Access behavior.

### Primary specification

[Intel 80960KB Programmer's Reference Manual, March 1988](https://www.arithmazium.org/classroom/lib/Intel_80960KB_Programmers_Reference_Manual_Mar88.pdf): printed pages 3-5, 11-67, 11-85, 11-110–111 and 11-117. Relevant instruction pages were read and visually checked. Source implementation is independently authored; no third-party emulator code was transplanted.

### Local test results

- Baseline before changes: 78 tests passed.
- Full suite after changes: **88 tests passed**.
- Ten new tests also passed with **Clang**, separately from GCC.
- New tests run compiled native instructions with undefined-behavior sanitization enabled.
- Shift oracle: **24,360 deterministic value/count cases per compiler**, with expectations generated independently in Python.
- Transfer tests cover all three widths, MEMA/MEMB addressing, scaled indexing, little-endian order, an address base overlapping load destinations, rejected partial-span writes/loads, missing callbacks, and untouched MMIO.

## Original-ROM measurements made in this pass

The supplied hotdo.7z matched all 29 expected chip sizes, CRC32 and SHA-1 values. Reconstructed maincpu SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

With unchanged roots 0x5F0 and 0x6B0, the same **3,051 static candidate addresses** were discovered. Native-emitting sites rose from **2,950 to 3,025**, leaving **26 unsupported**, down from 101. These are candidate code sites, not executed instruction coverage, hardware correctness, or a full-game completion percentage. All previously unsupported group-transfer and SHRI/SHRDI sites in this particular graph now emit native code.

Both actual-original-ROM regressions were compiled and executed locally:

| Configuration | Successful native steps | Controlled stop |
| --- | ---: | --- |
| Strict default | 1,904 | IP 0xA375C, serial TX write at 0x01C00014 |
| Documented TX enabled | 1,910 | IP 0xA372C, missing serial status at 0x01C0001A |

The second run recorded channel 2 byte FF and channel 1 byte 01. Both exited with the expected diagnostic status 3. No synthetic receive/status input was supplied to these regressions. ROM bytes, native game-derived C++, and executables are not included in the public commit.

## 2. Sega 315-5649 serial status — unresolved

This pass did not establish authentic HOTD1 receive bytes, buffer transitions or timing, and did not replace the stop with constant 0x0C or another fictional response.

A primary developer investigation, [MAME issue #11376](https://github.com/mamedev/mame/issues/11376), contains direct observations of differences between Model 2B physical hardware and emulation for serial/MIDI accesses. Its [discussion](https://github.com/mamedev/mame/issues/11376#issuecomment-1606146203) also reports tracing a serial connector through a transceiver toward 315-5649. It concerns a different game/board and different CPU-visible apertures, so it is **not** evidence that HOTD1's 0x01C0001A status can use those observed values. This is a useful warning against conflating distinct serial paths, not completion of our device model.

A falsifiable next experiment is to capture the original HOTD1 boot's two TX commands, status reads and corresponding RX bytes with cycle/order information. The existing synthetic fixtures cannot supply that missing evidence.

## 3. Board address 0x00F80000 — unidentified

Targeted public searches for this address and Sega Model 2/2C register documentation did not establish its decoding or effects. Absence from a software map is not proof that hardware ignores a write. No watchdog/reset/IRQ label has been assigned and no write has been discarded merely to advance boot.

The original ROM's store at IP 0x6B4 establishes that the game writes to this address. It does not, by itself, establish whether a device latches the value, ignores it, or changes timing/state. Resolving this still needs a board-specific register specification or a controlled physical observation. Issue #6 remains open.

## Reproduction

```sh
python -m unittest discover -s tests -v
CXX=clang++ python -m unittest discover -s tests -p test_i960_data_semantics.py -v
python -m arcaderecomp audit --layout targets/hotd1/original.json --rom /private/hotdo.7z
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp translate --layout targets/hotd1/original.json --rom /private/hotdo.7z --extra-entry 0x6b0 --limit 16384 --output build/hotd1/hotd1_i960.cpp
c++ -std=c++17 -O2 -Iruntime -Ibuild/hotd1 tools/hotd1_strict_boot_probe.cpp -o build/hotd1/strict_probe
build/hotd1/strict_probe build/hotd1/maincpu.bin 5000 --serial-tx
```

The last command intentionally stops with code 3 at unimplemented serial status. This pass is a CPU correctness/coverage improvement, **not** an authentic playable boot or a completed Model 2C platform.
