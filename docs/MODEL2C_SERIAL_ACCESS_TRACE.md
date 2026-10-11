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


### External serial provider failures

A connected status or RX provider can legitimately fail (for example,
disconnected hardware or a missing capture sample). Such exceptions now
become a structured, address-specific `DeviceAccessFault` at the native
CPU bus boundary. The diagnostic trace records a failed read with
`value_known=false`, not a successful zero or a guessed readiness bit.
Provider-specific exception messages are not copied into the game-side
fault report. A later successful read becomes observed **only** if the
provider explicitly returns a byte. This improves device-adapter
resilience; it adds no actual 315-5649 receive/status implementation.


### Atomic external TX observers (synthetic device-adapter contract)

External TX observers are now called **after** checking the explicit
observed-event buffer state but **before** any local transmit byte,
token, mux selector or transaction counter is committed. If the
observer throws a standard exception (such as a disconnected hardware
adapter), the bus reports an address-specific `DeviceAccessFault`
and the optional serial trace records a refused write. A retry may
succeed only if the observer explicitly accepts the byte. TX-full
writes never invoke the observer. This is a local software transaction
contract, not evidence that a real 315-5649 can retract bytes already
sent to the gun board. Callback success is not physical TX completion.


### Bounded capture and explicit evidence loss

The optional CPU-side access trace now retains a **first-in-session prefix**
of at most **4,096 observations** by default. Set the bound using
`StrictBus::set_serial_access_trace_limit(limit)` before tracing; a limit
of zero records only total and dropped counts. Capturing more transactions
never silently evicts earlier observations or changes the return from a
real serial provider. The diagnostic reports both retained and dropped
counts. It also exports a machine-readable terminal line:

    serial_trace_summary total=3 retained=3 dropped=0 truncated=no limit=4096

If the session exceeds its cap the report explicitly marks
`truncated=yes`. The Python serial-access comparator **rejects** such
records instead of guessing the missing traffic or treating it as a match.
Increasing the cap after truncation may retain later events with real
ordinals, never fabricated missing entries. Clearing the trace explicitly
resets ordinals and loss counters but does **not** reset serial device
state, completed transmissions or MMIO write logs. Disabling tracing
stops counting until recording is re-enabled.

This bounds the **CPU diagnostic trace only**. Long-running hardware
transmission and general bus write history use their own separate storage
and require independent limits for fully bounded runtime memory.
