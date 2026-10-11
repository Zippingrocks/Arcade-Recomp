# Model 2C serial CPU-access trace

ArcadeRecomp's partial Sega 315-5649 model deliberately refuses serial
status and RX data that no independent device/trace provider supplied.
The **opt-in CPU bus transaction trace** makes these refusals visible
without changing the partial hardware model or synthesizing a reply.

StrictBus::enable_serial_access_trace(true) enables logging; use
serial_access_trace() to inspect the ordered SerialBusAccess entries.
Each entry records:

- ordinal: CPU-side observed transaction sequence, **not** emulated cycles
- address, width, and read/write direction
- completed flag indicating successful bus transaction
- value_known flag; a refused read sets it to false
- value: a real observed return byte or an attempted CPU write value;
  never interpret the zero placeholder when value_known is false

The feature is disabled by default. A refused serial read/write and
unsupported width/lane are logged only when tracing is enabled; existing
DeviceAccessFault behavior is preserved. clear_serial_access_trace()
only resets the diagnostic history and does not touch 315-5649 buffers,
TX records, supplied RX events, or status.

The opt-in private strict boot probe enables this transaction trace when
--serial-tx is supplied. Against the authenticated original HOTD1 2-MiB
i960 main CPU image, the observed result is:

    executed=1910
    serial_access ordinal=1 direction=write address=0x1c00014 width=1 completed=yes value=0xff
    serial_access ordinal=2 direction=write address=0x1c00012 width=1 completed=yes value=0x1
    serial_access ordinal=3 direction=read address=0x1c0001a width=1 completed=no value=UNOBSERVED

The last line is NOT evidence for status 0x00. It is a failed hardware
read because no real status source was configured. No time, chip resets,
RS422 framing, lightgun response, ACK, or IRQ signaling are inferred.

ROM-free native regression tests run with GCC and Clang under UBSan in
tests/test_sega_serial_bus_trace.py and test_strict_boot_probe.py.
The original ROM-derived generated source, binaries and original
commercial ROM image remain private and are not checked into Git.
