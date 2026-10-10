# FLEX 8000 configuration input stages: PS, PPS and PPA

Date: 2026-10-10. Base commit: `437b9eb70f53e3ff7fc56c8848ab111fb97af44c`.

**Model 2C is NOT complete.** This pass implements a manufacturer-specified
functional portion of the FPGA loading interface, rather than another search
for lookup-table patterns. It does not identify which loading mode Sega wired
or connect any new response to the game's serial interface.

## Newly recovered specification and an important distinction

The project previously could not retrieve Altera AN33. Its text is now
available as [Altera Application Note 33, Configuring FLEX 8000 Devices,
June 2000 v3.03](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-).
The technical author is Altera; the host is a document mirror. The later
[FLEX 8000 datasheet, January 2003 v11.1](https://www.farnell.com/datasheets/134632.pdf),
printed pp. 53-54, independently inventories the loading modes and pins.

AN33's file descriptions (printed pp. 64-66) explicitly permit the same TTF
representation for PPA, PPS and bit-wide PS. The existing match between HOTD1's
upload and a compiler-produced TTF therefore identifies a data representation,
**not the FPGA's physical loading mode**. Serial transmission from the main
CPU to a gun board also does not prove that the final FPGA pin interface is
serial; an intervening device can change the transfer width.

The input modes have materially different behavior:

| Mode | Input event | Serialization/handshake |
| --- | --- | --- |
| PS: passive serial | DATA0 sampled on a rising host DCLK edge | No per-byte handshake; byte bits arrive least-significant first |
| PPS: passive parallel synchronous | Byte captured on first rising DCLK edge | Eight falling host DCLK edges serialize it; next byte captured on the ninth rising edge |
| PPA: passive parallel asynchronous | Selected byte captured on rising nWS | Internal clock serializes it; RDYnBUSY returns high on the eighth falling serialization-clock edge |

Sources: AN33 printed pp. 45-50 and 54-55. In PPA, selection requires CS high
and nCS low. During a valid nRS read, DATA7 carries RDYnBUSY. That single
status bit is not a license to fill the entire bus with a guessed byte.

Configuration-data loading and device initialization are also distinct. The
latter depends on configuration completion, CONF_DONE and initialization
clock/options. The mirrored PS completion paragraph has duplicated/garbled
wording, so this pass does not turn that paragraph into an exact end-of-stream
clock sequence. Neither physical completion nor the empirical record CRC
behavior has been implemented in the new input component.

## New original C++ implementation

`runtime/flex8000_config_ingress.hpp` provides three separately selected
input-stage implementations in a single small class. It has no dependency on
MAME, a game-specific bitstream, an i960 program counter or a Sega MMIO address.
Its algorithm was authored from the manufacturer descriptions above; no
third-party device implementation is included.

### Contract and supported behavior

The enclosing configuration controller must explicitly establish an active
loading window. `begin_loading()` is an integration boundary, **not a
simulation of power-on reset or nSTATUS**. Its documented entry contract
requires inactive strobes and a low clock after the parent has prepared the
FPGA for loading. Aborting a load clears the serializer; the enclosing
decoder must separately discard its already delivered bits.

Within that window, the component captures bytes/edges and derives PPA busy
state itself. Callers supply clock events, not invented status responses.
Repeated clock levels and repeated reads do not advance it. Writes while
busy, overlapping read/write strobes, and ambiguous simultaneous turnaround
are diagnostic errors before state changes. These rejections are software
safety boundaries, not claims about an undocumented silicon fault response.

PPS keeps its captured byte even if the input bus changes on later cycles.
PPA likewise retains its captured byte through bus changes and deselection.
The serializer emits abstract decoder-input bits, not a claimed extra device
pin. PPA exposes a masked DATA7 read; inactive/unselected buses are undriven.
`ready_nbusy()` returns no claimed value outside active PPA loading.

### Deliberate exclusions

This is event-ordered functional behavior, not nanosecond timing. Setup/hold
requirements, oscillator frequency/phase, propagation delays, power/reset,
mode strap sampling and electrical contention remain external. The class has
no CONF_DONE, nSTATUS, startup-complete or user-circuit-success API. It does
not know when a full configuration ends, validate hardware CRC, set routing
switches, initialize registers or acknowledge a Sega serial command.

Nothing in `model2c_bus.hpp` or `sega3155649_serial.hpp` was connected to it.
The existing provisional two-channel serial model is not validated merely
because these separate FPGA input stages pass their tests.

## Validation actually performed

The exact downloaded baseline source matched CI artifact SHA-256
`7c9aae4850af5684d14a8f8302062650f5217acde48806be38f4e26b26332868`.
Its full local baseline suite passed 253 tests.

Fourteen added tests exercise every possible input byte in all three modes,
correct and repeated edges, capture-before-bus-change, the eight-edge busy
boundary, read-side noninterference, all chip-select combinations, invalid
clock domains, every partial-byte abort position, independent instances,
invalid strobes, full report domains, ROM hash checks and input-file overwrite
protection. Native semantic cases run under both GCC and Clang with
UndefinedBehaviorSanitizer. CI uses synthetic bytes only.

### Original upload, explicitly synthetic pin stimulus

`arcaderecomp.config_ingress_probe` requires the verified original 2-MiB
CPU-image hash and 5,120-byte upload hash. It writes the private upload only
to a temporary local file, builds the native probe, and compares every emitted
bit in-process with the original byte sequence in LSB-first order.

With GCC and independently with Clang, all three modes passed:

| Measurement per compiler | Result |
| --- | ---: |
| Original upload bytes supplied separately to each mode | 5,120 |
| Decoder-input bits checked in PS | 40,960 |
| Decoder-input bits checked in PPS | 40,960 |
| Decoder-input bits checked in PPA | 40,960 |
| PPA busy observations before serialization edges | 40,960 |
| PPA masked DATA7 polls that must not advance state | 122,880 |
| Original source bytes/bit values exported in report | 0 |

Both compilers produced identical metadata. These are **original-upload tests
with synthetic pin and clock stimulus**, not original-cabinet captures,
execution of HOTD1's host routine, or proof of an accepted complete FPGA
configuration. All three passing is consistent with AN33's shared file
representation; it must not be used to choose a favorite wiring hypothesis.

The report is `docs/reports/hotdo_config_ingress.json`.

### Original game regression

The complete uploaded `hotdo.7z` again matched all 29 chip fingerprints.
A fresh AOT translation retained 3,051 candidate sites, 3,042 native-emitting
sites and nine unsupported sites, without reaching the graph cap. These are
static candidate counts, not a game-completion percentage.

The freshly compiled strict native probe returned diagnostic exit 3:

| Mode | Successful instructions | Deliberate stop |
| --- | ---: | --- |
| Strict default | 1,904 | Disabled first serial TX, IP 0xA375C |
| Documented TX only | 1,910 | Missing serial status 0x01C0001A, IP 0xA372C |

The second run recorded TX2=FF and TX1=01. Neither used a synthetic RX/status
provider. New input-stage code cannot move this boundary until the intervening
Sega transport and board wiring are established.

## Next specific evidence needed

For the actual 837-12079 gun sensor board, determine the EPF8282A mode straps
and the paths to DATA, DCLK/nWS, nRS, chip-select, nCONFIG, nSTATUS and
CONF_DONE. Sega's [original operator manual](https://www.mamechannel.it/files_free/arcade_manuals_unpacked/hotd.pdf)
names the board and RS422 link, but the existing evidence does not resolve
those internal connections. Main-CPU RX-ready flags must not be equated with
FPGA RDYnBUSY without that missing transport information.

A supported loading mode can then feed a framed configuration controller;
CRC/header/end-of-stream semantics and initialization require their own
validation. Routing, clocks, user logic, authentic gun responses and the
separate main-board register 0x00F80000 are still unresolved. No completion
gate or open hardware issue is being closed by this pass.

## Reproduce

```sh
python -m unittest discover -s tests -p 'test_flex8000_config_ingress.py' -v
python -m unittest discover -s tests -v
# Local original CPU image only; no uploads/network access:
python -m arcaderecomp.config_ingress_probe \
  --image build/hotd1/maincpu.bin \
  --output build/research/hotdo-config-ingress.json
```

The default original-data check requires both g++ and clang++; repeated
`--cxx` options select explicit alternatives. The native probe is under
`tools/experimental`. Private bytes and compiled diagnostic binaries are
not published. Passing the above commands is not a full game boot.
