"""Compiled synthetic tests for provisional Sega Model 2C IRQ registers.

No original Sega ROM bytes and no assertion of real CPU IRQ delivery.
All event inputs are explicitly created by test fixtures.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def compile_and_run(body):
    cxx = shutil.which("g++") or shutil.which("clang++")
    if cxx is None:
        raise unittest.SkipTest("Host C++17 compiler missing")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / "test.cpp"
        src.write_text('#include "model2c_bus.hpp"\n' + body, encoding="utf-8")
        exe = d / "test"
        result = subprocess.run(
            [cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime"), str(src), "-o", str(exe)],
            capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(result.stderr)
        result = subprocess.run([str(exe)], capture_output=True,
                                text=True, timeout=10)
        if result.returncode:
            raise AssertionError(f"Native exit {result.returncode}: {result.stderr}")

class PartialIRQRegisterTests(unittest.TestCase):
    def test_reset_opt_in_and_delayed_enable(self):
        compile_and_run(r"""
int main() {
    using namespace arcaderecomp_model2c;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    try { board.read(0x00e80000u, 4u); return 1; }
    catch (const DeviceAccessFault&) {}
    try { board.write(0x00e80004u, 4u, 0xfffu); return 2; }
    catch (const DeviceAccessFault&) {}
    board.enable_partial_irq_registers();
    if (board.read(0x00e80000u, 4u) || board.read(0x00e80004u, 4u)) return 3;
    board.write(0x00e80004u, 4u, 0xfffu);
    if (board.read(0x00e80004u, 4u)) return 4;
    board.irq_registers().advance_cpu_cycles(1u);
    if (board.read(0x00e80004u, 4u)) return 5;
    board.irq_registers().advance_cpu_cycles(1u);
    if (board.read(0x00e80004u, 4u) != 0xfffu) return 6;
    return 0;
}
""")

    def test_synthetic_irq_sources_acknowledge_and_pin_grouping(self):
        compile_and_run(r"""
int main() {
    using namespace arcaderecomp_model2c;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.enable_partial_irq_registers();
    board.write(0x00e80004u, 4u, 0xfffu);
    board.irq_registers().advance_cpu_cycles(2u);
    for (unsigned bit : {0u, 1u, 2u, 10u})
        board.irq_registers().inject_enabled_source_for_test(bit);
    if (board.read(0x00e80000u, 4u) != 0x407u) return 1;
    for (unsigned pin = 0; pin != 4; ++pin)
        if (!board.irq_registers().line_level(pin)) return 2;
    board.write(0x00e80000u, 4u, ~std::uint32_t(1u << 2));
    if (board.read(0x00e80000u, 4u) != 0x403u) return 3;
    if (board.irq_registers().line_level(2u)) return 4;
    board.write(0x00e80000u, 4u, 0u);
    if (board.read(0x00e80000u, 4u)) return 5;
    for (unsigned pin = 0; pin != 4; ++pin)
        if (board.irq_registers().line_level(pin)) return 6;
    return 0;
}
""")

    def test_no_implicit_clock_and_queued_mask_is_replaceable(self):
        compile_and_run(r"""
int main() {
    using namespace arcaderecomp_model2c;
    PartialIRQRegisters irq{};
    irq.request_enable_update(1u);
    irq.advance_cpu_cycles(1u);
    irq.request_enable_update(4u);
    irq.advance_cpu_cycles(1u);
    if (irq.enable() || irq.pending_enable_cycles() != 1u) return 1;
    irq.advance_cpu_cycles(1u);
    if (irq.enable() != 4u) return 2;
    irq.inject_enabled_source_for_test(0u);
    irq.inject_enabled_source_for_test(2u);
    if (irq.request() != 4u || !irq.line_level(2u)) return 3;
    try { irq.inject_enabled_source_for_test(12u); return 4; }
    catch (const std::out_of_range&) {}
    try { (void)irq.line_level(4u); return 5; }
    catch (const std::out_of_range&) {}
    return 0;
}
""")

    def test_unknown_irq_addresses_and_subword_accesses_still_fault(self):
        compile_and_run(r"""
int main() {
    using namespace arcaderecomp_model2c;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.enable_partial_irq_registers();
    for (auto address : {0x00e80000u, 0x00e80004u}) {
        try { board.write(address, 1u, 0u); return 1; }
        catch (const DeviceAccessFault&) {}
    }
    try { board.write(0x00e80002u, 4u, 0u); return 2; }
    catch (const DeviceAccessFault&) {}
    try { board.read(0x00e80008u, 4u); return 3; }
    catch (const DeviceAccessFault&) {}
    if (!board.writes().empty()) return 4;
    return 0;
}
""")

if __name__ == "__main__":
    unittest.main()
