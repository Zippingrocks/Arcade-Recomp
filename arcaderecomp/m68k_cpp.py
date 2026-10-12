"""Fixed-instruction MC68000 AOT C++ emission; no runtime opcode decoder."""
from dataclasses import dataclass

from .m68k import discover


@dataclass(frozen=True)
class TranslationReport:
    entry: int
    discovered: int
    translated: int
    unsupported: tuple[int, ...]
    limit_reached: bool


def _u(value):
    return f"0x{value & 0xffffffff:08x}u"


def _emit(ins):
    args, next_pc, op = ins.operands, _u(ins.next_pc), ins.mnemonic
    done = f"return finish(cpu, {next_pc});"
    if op == "nop":
        return done
    if op == "move_to_sr":
        return f"return move_sr(cpu, {args[0]}u, {next_pc});"
    if op == "moveq":
        reg, value = args
        return (f"cpu.d[{reg}] = {_u(value)}; cpu.d_known[{reg}] = 0xffffffffu; "
                f"logical_flags(cpu, {'true' if value < 0 else 'false'}, {'true' if value == 0 else 'false'}); {done}")
    if op == "clr_d":
        size, reg = args
        mask = _u((1 << (size * 8)) - 1)
        return (f"cpu.d[{reg}] &= ~{mask}; cpu.d_known[{reg}] |= {mask}; "
                f"logical_flags(cpu, false, true); {done}")
    if op == "movea_d":
        size, source, dest = args
        mask = "0xffffu" if size == 2 else "0xffffffffu"
        value = (f"((cpu.d[{source}] & 0x8000u) ? (cpu.d[{source}] | 0xffff0000u) : "
                 f"(cpu.d[{source}] & 0xffffu))") if size == 2 else f"cpu.d[{source}]"
        return (f"if ((cpu.d_known[{source}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state); "
                f"cpu.a[{dest}] = {value}; cpu.a_known[{dest}] = true; {done}")
    if op == "lea_absolute":
        dest, address = args
        return f"cpu.a[{dest}] = {_u(address)}; cpu.a_known[{dest}] = true; {done}"
    if op == "clr_byte_displacement":
        reg, displacement = args
        return (f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state); "
                f"const std::uint32_t address = (cpu.a[{reg}] + {_u(displacement)}) & 0x00ffffffu; "
                f"(void)bus.read8(address); bus.write8(address, 0); logical_flags(cpu, false, true); {done}")
    if op == "bcc":
        return (f"bool taken = false; if (!condition(cpu, {args[0]}u, taken)) return false; "
                f"return finish(cpu, taken ? {_u(ins.target)} : {next_pc});")
    if op == "dbcc":
        cc, reg = args
        return (f"bool terminate = false; if (!condition(cpu, {cc}u, terminate)) return false; "
                f"if (terminate) {{ {done} }} "
                f"if ((cpu.d_known[{reg}] & 0xffffu) != 0xffffu) return stop(cpu, Stop::undefined_state); "
                f"const std::uint32_t counter = (cpu.d[{reg}] - 1u) & 0xffffu; "
                f"cpu.d[{reg}] = (cpu.d[{reg}] & 0xffff0000u) | counter; "
                f"return finish(cpu, counter == 0xffffu ? {next_pc} : {_u(ins.target)});")
    return "return stop(cpu, Stop::" + ("untranslated_pc" if op == "invalid_fetch" else "unsupported_instruction") + ");"


def emit_cpp(image: bytes, entry: int, base: int = 0, limit: int = 4096):
    instructions, limited = discover(image, entry, base, limit)
    unsupported = tuple(i.pc for i in instructions if i.mnemonic in ("unsupported", "invalid_fetch"))
    source = ['#include "m68k_runtime.hpp"', "namespace arcaderecomp_m68k_generated {",
              "using namespace arcaderecomp::m68k;",
              "inline bool step(CPU& cpu, Bus& bus) {",
              "if (!execution_allowed(cpu)) return false;",
              "(void)bus; try { switch(cpu.pc) {"]
    for ins in instructions:
        source.append(f"case {_u(ins.pc)}: {{ {_emit(ins)} }}")
    source += ["default: return stop(cpu, Stop::untranslated_pc);", "}",
               "} catch(const BusFault& fault) {",
               "cpu.access_address = fault.address; cpu.access_write = fault.write;",
               "return stop(cpu, Stop::bus_access);", "}", "}", "}"]
    return "\n".join(source) + "\n", TranslationReport(entry, len(instructions),
        len(instructions) - len(unsupported), unsupported, limited)
