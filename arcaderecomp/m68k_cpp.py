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
    if op == "bsr":
        return f"return branch_subroutine(cpu, bus, {_u(ins.target)}, {next_pc});"
    if op == "rts":
        return "return return_subroutine(cpu, bus);"
    if op == "move_to_sr":
        return f"return move_sr(cpu, {args[0]}u, {next_pc});"
    if op == "moveq":
        reg, value = args
        return (f"cpu.d[{reg}] = {_u(value)}; cpu.d_known[{reg}] = 0xffffffffu; "
                f"logical_flags(cpu, {'true' if value < 0 else 'false'}, {'true' if value == 0 else 'false'}); {done}")
    if op == "logic_immediate_d":
        size, kind, reg, immediate = args
        return (f"return logic_immediate_d(cpu, {size}u, {kind}u, {reg}u, "
                f"{_u(immediate)}, {next_pc});")
    if op == "cmpi":
        size, immediate, mode, reg, displacement = args
        mask = _u((1 << (size * 8)) - 1)
        if mode == 0:
            fetch = (f"if ((cpu.d_known[{reg}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state); "
                     f"const std::uint32_t destination = cpu.d[{reg}] & {mask}; ")
        else:
            fetch = ""
            if mode in (2, 5):
                fetch += f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state); "
                address = f"cpu.a[{reg}] + {_u(displacement)}"
            else:
                address = _u(displacement)
            fetch += (f"std::uint32_t destination = 0; "
                      f"if (!read_operand(cpu, bus, {address}, {size}u, destination)) return false; ")
        return fetch + f"return compare_immediate(cpu, {size}u, destination, {_u(immediate)}, {next_pc});"
    if op == "move_memory_to_d":
        size, mode, source, displacement, dest = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        fetch = ""
        if mode in (2, 5):
            fetch = f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state); "
            address = f"cpu.a[{source}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        return (fetch + f"std::uint32_t value = 0; "
                f"if (!read_operand(cpu, bus, {address}, {size}u, value)) return false; "
                f"cpu.d[{dest}] = (cpu.d[{dest}] & ~{mask}) | value; cpu.d_known[{dest}] |= {mask}; "
                f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
    if op == "move_memory_postincrement":
        size, source, dest = args
        return (f"return move_memory_postincrement(cpu, bus, {size}u, {source}u, "
                f"{dest}u, {next_pc});")
    if op == "move":
        size, source_kind, source, mode, reg, displacement = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        statements = []
        if source_kind == 0:
            statements.append(f"if ((cpu.d_known[{source}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state);")
            value = f"cpu.d[{source}] & {mask}"
        else:
            value = _u(source)
        if mode == 5:
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
        statements.append(f"const std::uint32_t value = {value};")
        if mode == 0:
            statements.append(f"cpu.d[{reg}] = (cpu.d[{reg}] & ~{mask}) | value; cpu.d_known[{reg}] |= {mask};")
        else:
            address = f"cpu.a[{reg}] + {_u(displacement)}" if mode == 5 else _u(displacement)
            statements.append(f"if (!write_move(cpu, bus, {address}, {size}u, value)) return false;")
        statements += [f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "shift_immediate":
        size, reg, count, left, kind = args
        return (f"return shift_immediate(cpu, {size}u, {reg}u, {count}u, "
                f"{'true' if left else 'false'}, {'true' if kind == 3 else 'false'}, {next_pc});")
    if op == "clr_d":
        size, reg = args
        mask = _u((1 << (size * 8)) - 1)
        return (f"cpu.d[{reg}] &= ~{mask}; cpu.d_known[{reg}] |= {mask}; "
                f"logical_flags(cpu, false, true); {done}")
    if op == "movea":
        size, mode, source, dest, extra = args
        mask = "0xffffu" if size == 2 else "0xffffffffu"
        statements = []
        if mode == 0:
            statements.append(f"if ((cpu.d_known[{source}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state);")
            value = f"cpu.d[{source}]"
        elif mode == 1:
            statements.append(f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state);")
            value = f"cpu.a[{source}]"
        elif mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{source}] + {_u(extra)}"
            statements.append(f"std::uint32_t value = 0; if (!read_operand(cpu, bus, {address}, {size}u, value)) return false;")
            value = "value"
        elif mode == 7 and source in (0, 1):
            statements.append(f"std::uint32_t value = 0; if (!read_operand(cpu, bus, {_u(extra)}, {size}u, value)) return false;")
            value = "value"
        else:
            value = _u(extra)
        if size == 2:
            value = f"(({value} & 0x8000u) ? ({value} | 0xffff0000u) : ({value} & 0xffffu))"
        statements.append(f"cpu.a[{dest}] = {value}; cpu.a_known[{dest}] = true;")
        statements.append(done)
        return " ".join(statements)
    if op == "lea_absolute":
        dest, address = args
        return f"cpu.a[{dest}] = {_u(address)}; cpu.a_known[{dest}] = true; {done}"
    if op == "lea_displacement":
        source, dest, displacement = args
        return (f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state); "
                f"cpu.a[{dest}] = cpu.a[{source}] + {_u(displacement)}; "
                f"cpu.a_known[{dest}] = true; {done}")
    if op == "addq_d":
        size, dest, immediate = args
        return (f"return add_quick_data(cpu, {size}u, {dest}u, {immediate}u, "
                f"{next_pc});")
    if op == "clr_memory":
        size, mode, reg, displacement = args
        statements = []
        if mode in (2, 3, 5):
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(f"if (!clear_memory(cpu, bus, {address}, {size}u)) return false;")
        if mode == 3:
            increment = 2 if size == 1 and reg == 7 else size
            statements.append(f"cpu.a[{reg}] += {increment}u;")
        statements += ["logical_flags(cpu, false, true);", done]
        return " ".join(statements)
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
               "cpu.access_address = fault.address; cpu.access_write = fault.write; cpu.access_width = fault.width;",
               "return stop(cpu, Stop::bus_access);", "}", "}", "}"]
    return "\n".join(source) + "\n", TranslationReport(entry, len(instructions),
        len(instructions) - len(unsupported), unsupported, limited)
