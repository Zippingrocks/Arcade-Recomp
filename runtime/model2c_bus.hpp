// ArcadeRecomp: strict, independent Sega Model 2C i960-side memory bus.
//
// Only regions supported by published evidence are modeled. Unimplemented
// Sega I/O, geometry, interrupts, timers and other peripherals THROW instead
// of returning guessed zeroes. The CPU-control register backing store does
// not claim to reproduce physical wait-state timing.
//
// This header uses no MAME or other emulator source code, and contains no
// commercial game data.
#pragma once
#include "i960_frame_runtime.hpp"
#include "sega3155649_serial.hpp"
#include "model2c_irq_registers.hpp"
#include "model2c_timers.hpp"

#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace arcaderecomp_model2c {

enum class Region {
    program_rom,
    work_ram,
    cpu_control,
    game_data_rom,
    serial_io,
    irq_registers,
    timer_registers,
    geometry_interface,
    geometry_program_port,
    coprocessor_function_port,
    coprocessor_fifo_port,
    geometry_buffer,
    coprocessor_control,
    geometry_control,
    coprocessor_status,
    geometry_fifo_status,
    video_control,
    unmapped
};

static inline const char* region_name(Region region) {
    switch (region) {
    case Region::program_rom: return "i960 program ROM";
    case Region::work_ram: return "i960 work RAM";
    case Region::cpu_control: return "CPU wait-state control (timing pending)";
    case Region::game_data_rom: return "game data ROM";
    case Region::serial_io: return "Sega 315-5649 I/O controller (serial partial)";
    case Region::irq_registers: return "Model 2C IRQ request/enable registers (partial)";
    case Region::timer_registers: return "Model 2C countdown timer registers (partial)";
    case Region::geometry_interface: return "Model 2C geometry interface registers (unimplemented)";
    case Region::geometry_program_port: return "Model 2C geometry program/write port (unimplemented)";
    case Region::coprocessor_function_port: return "Model 2C coprocessor function port (unimplemented)";
    case Region::coprocessor_fifo_port: return "Model 2C TGPx4 upload/data FIFO port (unimplemented)";
    case Region::coprocessor_control: return "Model 2C TGPx4 control register (unimplemented)";
    case Region::geometry_control: return "Model 2C geometry control register (unimplemented)";
    case Region::coprocessor_status: return "Model 2C coprocessor status register (unimplemented)";
    case Region::geometry_buffer: return "Model 2C geometry buffer window (unimplemented)";
    case Region::geometry_fifo_status: return "Model 2C geometry FIFO status (unimplemented)";
    case Region::video_control: return "Model 2C video control registers (unimplemented)";
    case Region::unmapped: return "unmapped or unimplemented Model 2C device";
    }
    return "unknown";
}

struct DeviceAccessFault final : std::runtime_error {
    std::uint32_t address;
    unsigned width;
    bool write;
    Region region;

    DeviceAccessFault(std::uint32_t address_value, unsigned width_value,
                      bool is_write, Region region_value,
                      const char* reason)
        : std::runtime_error(message(address_value, width_value, is_write,
                                     region_value, reason)),
          address(address_value), width(width_value), write(is_write),
          region(region_value) {}

private:
    static std::string message(std::uint32_t address, unsigned width,
                               bool write, Region region, const char* reason) {
        std::ostringstream out;
        out << "Model 2C " << (write ? "write" : "read")
            << width * 8u << " @0x" << std::hex << std::setw(8)
            << std::setfill('0') << address << " [" << region_name(region)
            << "]: " << reason;
        return out.str();
    }
};

struct BusWrite {
    std::uint32_t address;
    std::uint32_t value;
    unsigned width;
    Region region;
};

// CPU-side transaction observations. Refused reads must not be confused
// with an observed status value of zero. Ordinals are not device cycles.
struct SerialBusAccess {
    std::uint64_t ordinal;
    std::uint32_t address;
    unsigned width;
    bool write;
    bool completed;
    bool value_known;
    std::uint32_t value;
};

class StrictBus final {
public:
    static constexpr std::uint32_t kProgramSize = 0x00200000u;
    static constexpr std::uint32_t kWorkStart = 0x00500000u;
    static constexpr std::uint32_t kWorkSize = 0x00100000u;
    static constexpr std::uint32_t kControlStart = 0x00e00000u;
    static constexpr std::uint32_t kControlSize = 0x38u;
    static constexpr std::uint32_t kDataStart = 0x02000000u;
    static constexpr std::uint32_t kDataSize = 0x02000000u;
    static constexpr std::uint32_t kExtraStart = 0x06000000u;
    static constexpr std::uint32_t kExtraSize = 0x01000000u;
    static constexpr std::uint32_t kIOStart = 0x01c00000u;
    static constexpr std::uint32_t kIOSize = 0x20u;
    // Published i960-visible Model 2C geometry apertures. Knowing an
    // address map is NOT permission to assume any FIFO/RAM side effects.
    static constexpr std::uint32_t kGeometryInterface = 0x00800000u;
    static constexpr std::uint32_t kGeometryInterfaceSize = 0x00004000u;
    static constexpr std::uint32_t kGeometryProgramPort = 0x00804000u;
    static constexpr std::uint32_t kCoproFunctionPort = 0x00880000u;
    static constexpr std::uint32_t kCoproFifoPort = 0x00884000u;
    static constexpr std::uint32_t kUploadPortSize = 0x00004000u;
    static constexpr std::uint32_t kCoproControl = 0x00980000u;
    static constexpr std::uint32_t kGeometryControl = 0x00980008u;
    static constexpr std::uint32_t kCoproStatus = 0x00980014u;
    static constexpr std::uint32_t kGeometryBuffer = 0x00900000u;
    static constexpr std::uint32_t kGeometryBufferSize = 0x00080000u;
    static constexpr std::uint32_t kGeometryFifoStatus = 0x00980004u;
    static constexpr std::uint32_t kVideoControl = 0x0098000cu;

    // Program ROM and optional 32-MiB mapped game-data ROM are user-supplied
    // and are never stored in this project's source tree.
    explicit StrictBus(std::vector<std::uint8_t> program,
                       std::vector<std::uint8_t> game_data = {})
        : program_(std::move(program)),
          work_(kWorkSize, 0u),
          control_(kControlSize, 0u),
          game_data_(std::move(game_data)) {
        if (program_.size() != kProgramSize)
            throw std::invalid_argument("Expected 2-MiB reconstructed i960 ROM image");
        if (!game_data_.empty() && game_data_.size() != kDataSize)
            throw std::invalid_argument("Optional game-data region must be exactly 32 MiB");
    }

    // Opt-in *partial* serial register access. Unknown IO and unprovided
    // serial receive bytes remain hard faults. Defaults to disabled.
    void enable_partial_serial_io(bool enabled = true) {
        serial_io_enabled_ = enabled;
    }
    // Opt-in research registers: NO real interrupt events or CPU delivery.
    void enable_partial_irq_registers(bool enabled = true) {
        irq_enabled_ = enabled;
    }
    void enable_partial_timers(bool enabled = true) { timers_enabled_ = enabled; }
    PartialModel2CTimers& timer_registers() { return timers_; }
    const PartialModel2CTimers& timer_registers() const { return timers_; }
    void advance_external_timer_ticks(std::uint64_t ticks) {
        if (!timers_enabled_)
            throw std::logic_error("timer model disabled; no implicit clock");
        timers_.advance_external_ticks(ticks, irq_, irq_enabled_);
    }
    PartialIRQRegisters& irq_registers() { return irq_; }
    const PartialIRQRegisters& irq_registers() const { return irq_; }
    IO3155649& serial_device() { return io_; }
    const IO3155649& serial_device() const { return io_; }

    // Research-only observational trace, never a serial reply provider.
    // Captures accepted and refused CPU bus accesses without advancing time.
    void enable_serial_access_trace(bool enabled = true) {
        serial_trace_enabled_ = enabled;
    }
    static constexpr std::size_t kDefaultSerialTraceLimit = 4096u;

    // A bounded, prefix-only diagnostic. Increasing the limit may resume
    // capture, but missing ordinal ranges are never silently filled in.
    // To start a fresh contiguous recording, explicitly clear the trace.
    void set_serial_access_trace_limit(std::size_t limit) {
        if (limit < serial_trace_.size())
            throw std::invalid_argument(
                "cannot shrink serial trace below already retained observations");
        serial_trace_limit_ = limit;
    }
    std::size_t serial_access_trace_limit() const { return serial_trace_limit_; }
    void clear_serial_access_trace() {
        serial_trace_.clear();
        serial_trace_total_ = 0u;
        serial_trace_dropped_ = 0u;
    }
    const std::vector<SerialBusAccess>& serial_access_trace() const {
        return serial_trace_;
    }
    std::uint64_t serial_access_trace_total() const { return serial_trace_total_; }
    std::uint64_t serial_access_trace_dropped() const { return serial_trace_dropped_; }
    bool serial_access_trace_truncated() const { return serial_trace_dropped_ != 0u; }

    arcaderecomp_generated::Bus callbacks() {
        return arcaderecomp_generated::Bus{
            this, &bridge_read32, &bridge_write32, &bridge_read8,
            &bridge_write8, &bridge_read16, &bridge_write16,
            &bridge_read32_sync
        };
    }

    Region classify(std::uint32_t address) const {
        if (inside(address, 0u, kProgramSize)) return Region::program_rom;
        if (inside(address, kWorkStart, kWorkSize)) return Region::work_ram;
        if (inside(address, kControlStart, kControlSize)) return Region::cpu_control;
        if (inside(address, kGeometryInterface, kGeometryInterfaceSize))
            return Region::geometry_interface;
        if (inside(address, kGeometryProgramPort, kUploadPortSize))
            return Region::geometry_program_port;
        if (inside(address, kCoproFunctionPort, kUploadPortSize))
            return Region::coprocessor_function_port;
        if (inside(address, kCoproFifoPort, kUploadPortSize))
            return Region::coprocessor_fifo_port;
        if (inside(address, kGeometryBuffer, kGeometryBufferSize))
            return Region::geometry_buffer;
        if (inside(address, kCoproControl, 4u))
            return Region::coprocessor_control;
        if (inside(address, kGeometryControl, 4u))
            return Region::geometry_control;
        if (inside(address, kCoproStatus, 4u))
            return Region::coprocessor_status;
        if (inside(address, kGeometryFifoStatus, 4u))
            return Region::geometry_fifo_status;
        if (inside(address, kVideoControl, 4u))
            return Region::video_control;
        if (inside(address, kIOStart, kIOSize)) return Region::serial_io;
        if (inside(address, PartialModel2CTimers::BASE, 16u)) return Region::timer_registers;
        if (inside(address, PartialIRQRegisters::REQUEST, 8u))
            return Region::irq_registers;
        if (inside(address, kDataStart, kDataSize) ||
            inside(address, kExtraStart, kExtraSize)) return Region::game_data_rom;
        return Region::unmapped;
    }

    std::uint32_t read(std::uint32_t address, unsigned width) const {
        return read_value(address, width);
    }

    void write(std::uint32_t address, unsigned width, std::uint32_t value) {
        const auto reg = classify(address);
        if (reg == Region::serial_io) {
            try {
                validate_access(address, width, true, reg);
                io_.write_bus_byte(address, static_cast<std::uint8_t>(value));
            } catch (const IO3155649::Unsupported& error) {
                record_serial_access(address, width, true, false, true, value);
                throw DeviceAccessFault(address, width, true, reg, error.what());
            } catch (const DeviceAccessFault&) {
                record_serial_access(address, width, true, false, true, value);
                throw;
            }
            record_serial_access(address, width, true, true, true, value);
            writes_.push_back({address, value, width, reg});
            return;
        }
        validate_access(address, width, true, reg);
        if (reg == Region::timer_registers) {
            try { timers_.write(address, value); }
            catch (const PartialModel2CTimers::Unverified& error) {
                throw DeviceAccessFault(address, width, true, reg, error.what());
            }
            writes_.push_back({address, value, width, reg});
            return;
        }
        if (reg == Region::irq_registers) {
            if (address == PartialIRQRegisters::REQUEST)
                irq_.acknowledge(value);
            else if (address == PartialIRQRegisters::ENABLE)
                irq_.request_enable_update(value);
            else
                throw DeviceAccessFault(address, width, true, reg,
                                        "unsupported IRQ register address");
            writes_.push_back({address, value, width, reg});
            return;
        }
        if (reg != Region::work_ram && reg != Region::cpu_control)
            throw DeviceAccessFault(address, width, true, reg, "read-only or unimplemented device");
        auto& array = reg == Region::work_ram ? work_ : control_;
        const auto base = region_offset(address, reg);
        for (unsigned i = 0; i < width; ++i)
            array[base + i] = static_cast<std::uint8_t>(value >> (8u * i));
        if (reg == Region::cpu_control)
            ++pending_timing_writes_;
        writes_.push_back({address, value, width, reg});
    }

    const std::vector<BusWrite>& writes() const { return writes_; }
    std::size_t pending_timing_writes() const { return pending_timing_writes_; }
    const std::vector<std::uint8_t>& program() const { return program_; }

private:
    std::vector<std::uint8_t> program_;
    std::vector<std::uint8_t> work_;
    std::vector<std::uint8_t> control_;
    std::vector<std::uint8_t> game_data_;
    std::vector<BusWrite> writes_;
    std::size_t pending_timing_writes_ = 0;
    bool serial_io_enabled_ = false;
    IO3155649 io_{};
    bool serial_trace_enabled_ = false;
    std::size_t serial_trace_limit_ = kDefaultSerialTraceLimit;
    mutable std::vector<SerialBusAccess> serial_trace_{};
    mutable std::uint64_t serial_trace_total_ = 0u;
    mutable std::uint64_t serial_trace_dropped_ = 0u;

    void record_serial_access(std::uint32_t address, unsigned width,
                              bool write, bool completed, bool value_known,
                              std::uint32_t value) const {
        if (!serial_trace_enabled_) return;
        // The trace is diagnostic, never a provider of device responses.
        // Stop retaining new entries at the cap, but preserve the
        // total transaction count and an explicit evidence-loss flag.
        if (serial_trace_total_ == UINT64_MAX)
            throw std::overflow_error("serial trace ordinal exhausted");
        const auto ordinal = ++serial_trace_total_;
        if (serial_trace_.size() >= serial_trace_limit_) {
            ++serial_trace_dropped_;
            return;
        }
        serial_trace_.push_back({
            ordinal, address, width, write, completed, value_known, value
        });
    }
    bool irq_enabled_ = false;
    PartialIRQRegisters irq_{};
    bool timers_enabled_ = false;
    PartialModel2CTimers timers_{};

    static bool inside(std::uint32_t address, std::uint32_t start,
                       std::uint32_t length) {
        return address >= start && address - start < length;
    }

    static std::size_t region_offset(std::uint32_t address, Region reg) {
        switch (reg) {
        case Region::program_rom: return address;
        case Region::work_ram: return address - kWorkStart;
        case Region::cpu_control: return address - kControlStart;
        case Region::serial_io: return address - kIOStart;
        case Region::game_data_rom:
            return inside(address, kExtraStart, kExtraSize)
                ? 0x01000000u + address - kExtraStart
                : address - kDataStart;
        default: return 0;
        }
    }

    std::size_t region_remaining(std::uint32_t address, Region reg) const {
        switch (reg) {
        case Region::program_rom: return kProgramSize - address;
        case Region::work_ram: return kWorkSize - (address - kWorkStart);
        case Region::cpu_control: return kControlSize - (address - kControlStart);
        case Region::serial_io: return kIOSize - (address - kIOStart);
        case Region::irq_registers:
            return 8u - (address - PartialIRQRegisters::REQUEST);
        case Region::timer_registers:
            return 16u - (address - PartialModel2CTimers::BASE);
        case Region::geometry_interface:
            return kGeometryInterfaceSize - (address - kGeometryInterface);
        case Region::geometry_program_port:
            return kUploadPortSize - (address - kGeometryProgramPort);
        case Region::coprocessor_function_port:
            return kUploadPortSize - (address - kCoproFunctionPort);
        case Region::coprocessor_fifo_port:
            return kUploadPortSize - (address - kCoproFifoPort);
        case Region::coprocessor_control:
            return 4u - (address - kCoproControl);
        case Region::geometry_control:
            return 4u - (address - kGeometryControl);
        case Region::coprocessor_status:
            return 4u - (address - kCoproStatus);
        case Region::geometry_buffer:
            return kGeometryBufferSize - (address - kGeometryBuffer);
        case Region::geometry_fifo_status:
            return 4u - (address - kGeometryFifoStatus);
        case Region::video_control:
            return 4u - (address - kVideoControl);
        case Region::game_data_rom:
            if (inside(address, kExtraStart, kExtraSize))
                return kExtraSize - (address - kExtraStart);
            return kDataSize - (address - kDataStart);
        default: return 0;
        }
    }

    void validate_access(std::uint32_t address, unsigned width, bool write,
                         Region reg) const {
        if (width != 1u && width != 2u && width != 4u)
            throw std::invalid_argument("Expected a byte, halfword or word bus transaction");
        // Until the i960's unaligned-fault masking is modeled, refuse
        // uncertain misaligned bus behavior rather than returning a guess.
        if (width > 1 && (address % width) != 0)
            throw DeviceAccessFault(address, width, write, reg, "unaligned transfer unsupported");
        if (reg == Region::timer_registers) {
            if (!timers_enabled_ || width != 4u ||
                ((address - PartialModel2CTimers::BASE) & 3u) != 0u)
                throw DeviceAccessFault(address, width, write, reg,
                                        "timer disabled or unverified access width");
        }
        if (reg == Region::irq_registers) {
            if (!irq_enabled_ || width != 4u ||
                (address != PartialIRQRegisters::REQUEST &&
                 address != PartialIRQRegisters::ENABLE))
                throw DeviceAccessFault(address, width, write, reg,
                                        "IRQ controller disabled/unknown width");
        }
        if (reg == Region::serial_io) {
            if (!serial_io_enabled_ || width != 1u)
                throw DeviceAccessFault(address, width, write, reg,
                                        "partial serial device disabled or unsupported width");
        }
        if (reg == Region::unmapped)
            throw DeviceAccessFault(address, width, write, reg, "unmapped access");
        if (region_remaining(address, reg) < width)
            throw DeviceAccessFault(address, width, write, reg, "crosses region boundary");
        if (reg == Region::game_data_rom && game_data_.empty())
            throw DeviceAccessFault(address, width, write, reg, "data ROM not supplied");
        if (write && (reg == Region::program_rom || reg == Region::game_data_rom))
            throw DeviceAccessFault(address, width, true, reg, "ROM is read-only");
        // This classification only improves fault provenance. In particular,
        // the mirrored geometry window must NOT be treated as generic RAM;
        // FIFO fullness, coprocessor uploads and video timing are unknown.
        if (reg == Region::geometry_interface ||
            reg == Region::geometry_program_port ||
            reg == Region::coprocessor_function_port ||
            reg == Region::coprocessor_fifo_port ||
            reg == Region::coprocessor_control ||
            reg == Region::geometry_control ||
            reg == Region::coprocessor_status ||
            reg == Region::geometry_buffer ||
            reg == Region::geometry_fifo_status ||
            reg == Region::video_control)
            throw DeviceAccessFault(address, width, write, reg,
                                    "geometry/video hardware behavior unimplemented");
    }

    const std::vector<std::uint8_t>* readable_bytes(std::uint32_t address,
                                                     Region reg) const {
        switch (reg) {
        case Region::program_rom: return &program_;
        case Region::work_ram: return &work_;
        case Region::cpu_control: return &control_;
        case Region::game_data_rom: return &game_data_;
        default:
            throw DeviceAccessFault(address, 1, false, reg, "device unavailable");
        }
    }

    std::uint32_t read_value(std::uint32_t address, unsigned width) const {
        const auto reg = classify(address);
        if (reg == Region::serial_io) {
            try {
                validate_access(address, width, false, reg);
                const auto value = io_.read_bus_byte(address);
                record_serial_access(address, width, false, true, true, value);
                return value;
            } catch (const IO3155649::Unsupported& error) {
                record_serial_access(address, width, false, false, false, 0u);
                throw DeviceAccessFault(address, width, false, reg, error.what());
            } catch (const DeviceAccessFault&) {
                record_serial_access(address, width, false, false, false, 0u);
                throw;
            }
        }
        validate_access(address, width, false, reg);
        if (reg == Region::timer_registers) {
            try { return timers_.read(address); }
            catch (const PartialModel2CTimers::Unverified& error) {
                throw DeviceAccessFault(address, width, false, reg, error.what());
            }
        }
        if (reg == Region::irq_registers) {
            if (address == PartialIRQRegisters::REQUEST)
                return irq_.request();
            if (address == PartialIRQRegisters::ENABLE)
                return irq_.enable();
            throw DeviceAccessFault(address, width, false, reg,
                                    "unsupported IRQ register address");
        }
        const auto* array = readable_bytes(address, reg);
        const auto base = region_offset(address, reg);
        std::uint32_t result = 0;
        for (unsigned i = 0; i < width; ++i)
            result |= std::uint32_t((*array)[base + i]) << (8u * i);
        return result;
    }

    // Explicitly completed plain ROM/RAM reads only. No wait-state register,
    // serial I/O or unknown device is treated as synchronous ordinary memory.
    // This is a functional memory model, NOT exact bus-cycle timing.
    static bool bridge_read32_sync(void* context, std::uint32_t address,
                                   std::uint32_t* destination) {
        if (!destination) return false;
        auto* board = static_cast<StrictBus*>(context);
        const Region reg = board->classify(address);
        if (reg != Region::program_rom && reg != Region::work_ram &&
            reg != Region::game_data_rom) return false;
        try {
            const std::uint32_t value = board->read_value(address, 4u);
            *destination = value;
            return true;
        } catch (const DeviceAccessFault&) {
            return false;
        }
    }
    static std::uint32_t bridge_read32(void* p, std::uint32_t a) {
        return static_cast<StrictBus*>(p)->read_value(a, 4);
    }
    static void bridge_write32(void* p, std::uint32_t a, std::uint32_t v) {
        static_cast<StrictBus*>(p)->write(a, 4, v);
    }
    static std::uint8_t bridge_read8(void* p, std::uint32_t a) {
        return static_cast<std::uint8_t>(static_cast<StrictBus*>(p)->read_value(a, 1));
    }
    static void bridge_write8(void* p, std::uint32_t a, std::uint8_t v) {
        static_cast<StrictBus*>(p)->write(a, 1, v);
    }
    static std::uint16_t bridge_read16(void* p, std::uint32_t a) {
        return static_cast<std::uint16_t>(static_cast<StrictBus*>(p)->read_value(a, 2));
    }
    static void bridge_write16(void* p, std::uint32_t a, std::uint16_t v) {
        static_cast<StrictBus*>(p)->write(a, 2, v);
    }
};

} // namespace arcaderecomp_model2c
