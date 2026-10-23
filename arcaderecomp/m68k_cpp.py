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
    if op == "rte":
        return "return return_exception(cpu, bus);"
    if op == "jmp_a":
        reg = args[0]
        return (f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state); "
                f"return finish(cpu, cpu.a[{reg}]);")
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
    if op == "addi_d":
        size, reg, immediate = args
        return (f"return add_immediate_data(cpu, {size}u, {reg}u, "
                f"{_u(immediate)}, {next_pc});")
    if op == "subi_d":
        size, reg, immediate = args
        return (f"return subtract_immediate_data(cpu, {size}u, {reg}u, "
                f"{_u(immediate)}, {next_pc});")
    if op == "or_d":
        size, source, destination = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        return (f"if ((cpu.d_known[{source}] & {mask}) != {mask} || "
                f"(cpu.d_known[{destination}] & {mask}) != {mask}) "
                f"return stop(cpu, Stop::undefined_state); "
                f"const std::uint32_t result = (cpu.d[{source}] | "
                f"cpu.d[{destination}]) & {mask}; "
                f"cpu.d[{destination}] = (cpu.d[{destination}] & ~{mask}) | result; "
                f"cpu.d_known[{destination}] |= {mask}; "
                f"logical_flags(cpu, (result & {sign}) != 0u, result == 0u); {done}")
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
    if op == "btst_immediate":
        bit, mode, reg, displacement = args
        selected = bit & (31 if mode == 0 else 7)
        bit_mask = _u(1 << selected)
        if mode == 0:
            return (f"if ((cpu.d_known[{reg}] & {bit_mask}) != {bit_mask}) "
                    f"return stop(cpu, Stop::undefined_state); "
                    f"const bool zero = (cpu.d[{reg}] & {bit_mask}) == 0; "
                    f"cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~4u) | (zero ? 4u : 0u)); "
                    f"cpu.sr_known |= 4u; {done}")
        statements = []
        if mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(f"std::uint32_t value = 0; if (!read_operand(cpu, bus, {address}, 1u, value)) return false;")
        statements.append(f"const bool zero = (value & {bit_mask}) == 0;")
        statements += ["cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~4u) | (zero ? 4u : 0u)); cpu.sr_known |= 4u;", done]
        return " ".join(statements)
    if op == "bclr_immediate_d":
        bit, reg = args
        bit_mask = _u(1 << (bit & 31))
        return (f"if ((cpu.d_known[{reg}] & {bit_mask}) != {bit_mask}) "
                f"return stop(cpu, Stop::undefined_state); "
                f"const bool zero = (cpu.d[{reg}] & {bit_mask}) == 0u; "
                f"cpu.d[{reg}] &= ~{bit_mask}; cpu.d_known[{reg}] |= {bit_mask}; "
                f"cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~4u) | "
                f"(zero ? 4u : 0u)); cpu.sr_known |= 4u; {done}")
    if op == "bset_immediate_memory":
        bit, mode, reg, displacement = args
        if mode in (2, 5):
            prefix = (f"if (!cpu.a_known[{reg}]) "
                      f"return stop(cpu, Stop::undefined_state); ")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            prefix, address = "", _u(displacement)
        return (prefix + f"return bit_set_immediate_memory(cpu, bus, {address}, "
                f"{bit}u, {next_pc});")
    if op == "bset_immediate_indexed":
        bit, base, extension = args
        return (f"std::uint32_t address = 0; if (!indexed_address(cpu, "
                f"{base}u, {extension}u, address)) return false; "
                f"return bit_set_immediate_memory(cpu, bus, address, {bit}u, "
                f"{next_pc});")
    if op == "move_memory_to_d":
        size, mode, source, displacement, dest = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        fetch = ""
        if mode in (2, 3, 5):
            fetch = f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state); "
            address = f"cpu.a[{source}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        update = ""
        if mode == 3:
            increment = 2 if size == 1 and source == 7 else size
            update = f"cpu.a[{source}] += {increment}u; "
        return (fetch + f"std::uint32_t value = 0; "
                f"if (!read_operand(cpu, bus, {address}, {size}u, value)) return false; " + update +
                f"cpu.d[{dest}] = (cpu.d[{dest}] & ~{mask}) | value; cpu.d_known[{dest}] |= {mask}; "
                f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
    if op == "move_indexed_to_d":
        size, base, dest, extension = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        return (f"std::uint32_t address = 0; if (!indexed_address(cpu, {base}u, "
                f"{extension}u, address)) return false; std::uint32_t value = 0; "
                f"if (!read_operand(cpu, bus, address, {size}u, value)) return false; "
                f"cpu.d[{dest}] = (cpu.d[{dest}] & ~{mask}) | value; "
                f"cpu.d_known[{dest}] |= {mask}; "
                f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
    if op == "move_memory_to_memory":
        (size, source_mode, source, source_displacement, destination_mode,
         destination, destination_displacement) = args
        sign = _u(1 << (size * 8 - 1))
        statements = []
        if source_mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state);")
            source_address = f"cpu.a[{source}] + {_u(source_displacement)}"
        else:
            source_address = _u(source_displacement)
        if destination_mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{destination}]) return stop(cpu, Stop::undefined_state);")
            destination_address = f"cpu.a[{destination}] + {_u(destination_displacement)}"
        else:
            destination_address = _u(destination_displacement)
        statements.append(
            f"std::uint32_t value = 0; if (!read_operand(cpu, bus, "
            f"{source_address}, {size}u, value)) return false;")
        statements.append(
            f"if (!write_move(cpu, bus, {destination_address}, {size}u, "
            f"value)) return false;")
        statements += [f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "move_memory_postincrement":
        size, source, dest = args
        return (f"return move_memory_postincrement(cpu, bus, {size}u, {source}u, "
                f"{dest}u, {next_pc});")
    if op == "move_postincrement_to_memory":
        size, source, mode, destination, displacement = args
        sign = _u(1 << (size * 8 - 1))
        statements = [
            f"if (!cpu.a_known[{source}]) "
            f"return stop(cpu, Stop::undefined_state);"]
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{destination}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{destination}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        increment = 2 if size == 1 and source == 7 else size
        statements.append(
            f"std::uint32_t value = 0; if (!read_operand(cpu, bus, "
            f"cpu.a[{source}], {size}u, value)) return false;")
        statements.append(f"cpu.a[{source}] += {increment}u;")
        statements.append(
            f"if (!write_move(cpu, bus, {address}, {size}u, value)) "
            f"return false;")
        statements += [
            f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "move_postincrement_to_indexed":
        size, source, base, extension = args
        return (f"return move_postincrement_to_indexed(cpu, bus, {size}u, "
                f"{source}u, {base}u, {extension}u, {next_pc});")
    if op == "move_indexed_to_postincrement":
        size, base, destination, extension = args
        return (f"return move_indexed_to_postincrement(cpu, bus, {size}u, "
                f"{base}u, {destination}u, {extension}u, {next_pc});")
    if op == "move_address_to_d":
        size, source, dest = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        return (f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state); "
                f"const std::uint32_t value = cpu.a[{source}] & {mask}; "
                f"cpu.d[{dest}] = (cpu.d[{dest}] & ~{mask}) | value; "
                f"cpu.d_known[{dest}] |= {mask}; "
                f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
    if op == "move_address_to_memory":
        size, source, mode, reg, displacement = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        statements = [f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state);"]
        if mode in (2, 3, 5):
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(f"const std::uint32_t value = cpu.a[{source}] & {mask};")
        statements.append(f"if (!write_move(cpu, bus, {address}, {size}u, value)) return false;")
        statements += [f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "move":
        size, source_kind, source, mode, reg, displacement = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        statements = []
        if source_kind == 0:
            statements.append(f"if ((cpu.d_known[{source}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state);")
            value = f"cpu.d[{source}] & {mask}"
        else:
            value = _u(source)
        if mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
        statements.append(f"const std::uint32_t value = {value};")
        if mode == 0:
            statements.append(f"cpu.d[{reg}] = (cpu.d[{reg}] & ~{mask}) | value; cpu.d_known[{reg}] |= {mask};")
        else:
            address = (f"cpu.a[{reg}] + {_u(displacement)}"
                       if mode in (2, 3, 5) else _u(displacement))
            statements.append(f"if (!write_move(cpu, bus, {address}, {size}u, value)) return false;")
            if mode == 3:
                increment = 2 if size == 1 and reg == 7 else size
                statements.append(f"cpu.a[{reg}] += {increment}u;")
        statements += [f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "move_d_to_indexed":
        size, source, base, extension = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        return (f"if ((cpu.d_known[{source}] & {mask}) != {mask}) "
                f"return stop(cpu, Stop::undefined_state); "
                f"std::uint32_t address = 0; if (!indexed_address(cpu, {base}u, "
                f"{extension}u, address)) return false; "
                f"const std::uint32_t value = cpu.d[{source}] & {mask}; "
                f"if (!write_move(cpu, bus, address, {size}u, value)) return false; "
                f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
    if op == "shift_immediate":
        size, reg, count, left, kind = args
        return (f"return shift_immediate(cpu, {size}u, {reg}u, {count}u, "
                f"{'true' if left else 'false'}, {'true' if kind == 3 else 'false'}, {next_pc});")
    if op == "logical_shift_register":
        size, destination, count_register, left = args
        return (f"return logical_shift_register(cpu, {size}u, {destination}u, "
                f"{count_register}u, {'true' if left else 'false'}, {next_pc});")
    if op == "clr_d":
        size, reg = args
        mask = _u((1 << (size * 8)) - 1)
        return (f"cpu.d[{reg}] &= ~{mask}; cpu.d_known[{reg}] |= {mask}; "
                f"logical_flags(cpu, false, true); {done}")
    if op == "tst":
        size, mode, reg, displacement = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        if mode == 0:
            return (f"if ((cpu.d_known[{reg}] & {mask}) != {mask}) "
                    f"return stop(cpu, Stop::undefined_state); "
                    f"const std::uint32_t value = cpu.d[{reg}] & {mask}; "
                    f"logical_flags(cpu, (value & {sign}) != 0, value == 0); {done}")
        statements = []
        if mode in (2, 3, 5):
            statements.append(f"if (!cpu.a_known[{reg}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(f"std::uint32_t value = 0; if (!read_operand(cpu, bus, {address}, {size}u, value)) return false;")
        if mode == 3:
            increment = 2 if size == 1 and reg == 7 else size
            statements.append(f"cpu.a[{reg}] += {increment}u;")
        statements += [f"logical_flags(cpu, (value & {sign}) != 0, value == 0);", done]
        return " ".join(statements)
    if op == "negx_d":
        size, reg = args
        return f"return negate_extend_data(cpu, {size}u, {reg}u, {next_pc});"
    if op == "neg_d":
        size, reg = args
        return f"return negate_data(cpu, {size}u, {reg}u, {next_pc});"
    if op == "swap_d":
        reg, = args
        return f"return swap_data(cpu, {reg}u, {next_pc});"
    if op == "movem_store":
        size, base, mask, predecrement = args
        return (f"return movem_store(cpu, bus, {size}u, {base}u, {mask}u, "
                f"{'true' if predecrement else 'false'}, {next_pc});")
    if op == "movem_load_postincrement":
        size, base, mask = args
        return (f"return movem_load_postincrement(cpu, bus, {size}u, "
                f"{base}u, {mask}u, {next_pc});")
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
    if op == "movea_indexed":
        size, base, dest, extension = args
        value = ("((value & 0x8000u) ? (value | 0xffff0000u) : "
                 "(value & 0xffffu))" if size == 2 else "value")
        return (f"std::uint32_t address = 0; if (!indexed_address(cpu, {base}u, "
                f"{extension}u, address)) return false; std::uint32_t value = 0; "
                f"if (!read_operand(cpu, bus, address, {size}u, value)) return false; "
                f"cpu.a[{dest}] = {value}; cpu.a_known[{dest}] = true; {done}")
    if op == "lea_absolute":
        dest, address = args
        return f"cpu.a[{dest}] = {_u(address)}; cpu.a_known[{dest}] = true; {done}"
    if op == "lea_displacement":
        source, dest, displacement = args
        return (f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state); "
                f"cpu.a[{dest}] = cpu.a[{source}] + {_u(displacement)}; "
                f"cpu.a_known[{dest}] = true; {done}")
    if op == "lea_pc_indexed":
        dest, extension = args
        return (f"std::uint32_t address = 0; if (!indexed_pc_address(cpu, "
                f"{_u(ins.pc + 2)}, {extension}u, address)) return false; "
                f"cpu.a[{dest}] = address; cpu.a_known[{dest}] = true; {done}")
    if op == "adda_d":
        size, source, dest = args
        mask = "0xffffu" if size == 2 else "0xffffffffu"
        value = (f"((cpu.d[{source}] & 0x8000u) ? "
                 f"(cpu.d[{source}] | 0xffff0000u) : "
                 f"(cpu.d[{source}] & 0xffffu))" if size == 2 else
                 f"cpu.d[{source}]")
        return (f"if ((cpu.d_known[{source}] & {mask}) != {mask} || "
                f"!cpu.a_known[{dest}]) return stop(cpu, Stop::undefined_state); "
                f"cpu.a[{dest}] += {value}; {done}")
    if op == "sub_d":
        size, source, dest = args
        return (f"return subtract_data(cpu, {size}u, {source}u, {dest}u, "
                f"{next_pc});")
    if op == "add_d":
        size, source, dest = args
        return (f"return add_data(cpu, {size}u, {source}u, {dest}u, "
                f"{next_pc});")
    if op == "mulu_d":
        source, destination = args
        return (f"return multiply_unsigned_word(cpu, {source}u, "
                f"{destination}u, {next_pc});")
    if op == "mulu_immediate":
        source, destination = args
        return (f"return multiply_unsigned_word_immediate(cpu, {source}u, "
                f"{destination}u, {next_pc});")
    if op == "add_memory_to_d":
        size, mode, source, displacement, destination = args
        mask = _u((1 << (size * 8)) - 1)
        statements = [
            f"if ((cpu.d_known[{destination}] & {mask}) != {mask}) "
            f"return stop(cpu, Stop::undefined_state);"]
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{source}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{source}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(
            f"std::uint32_t source_value = 0; if (!read_operand(cpu, bus, "
            f"{address}, {size}u, source_value)) return false;")
        statements.append(
            f"return add_immediate_data(cpu, {size}u, {destination}u, "
            f"source_value, {next_pc});")
        return " ".join(statements)
    if op == "add_d_to_memory":
        size, source, mode, destination, displacement = args
        statements = []
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{destination}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{destination}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(
            f"return add_data_memory(cpu, bus, {address}, {size}u, "
            f"{source}u, {next_pc});")
        return " ".join(statements)
    if op in ("add_d_to_indexed", "sub_d_to_indexed"):
        size, source, base, extension = args
        helper = "add_data_memory" if op.startswith("add") else "subtract_data_memory"
        return (f"std::uint32_t address = 0; if (!indexed_address(cpu, "
                f"{base}u, {extension}u, address)) return false; return "
                f"{helper}(cpu, bus, address, {size}u, {source}u, "
                f"{next_pc});")
    if op == "sub_d_to_memory":
        size, source, mode, destination, displacement = args
        statements = []
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{destination}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{destination}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(
            f"return subtract_data_memory(cpu, bus, {address}, {size}u, "
            f"{source}u, {next_pc});")
        return " ".join(statements)
    if op == "or_memory_to_d":
        size, mode, source, displacement, destination = args
        mask, sign = _u((1 << (size * 8)) - 1), _u(1 << (size * 8 - 1))
        statements = [f"if ((cpu.d_known[{destination}] & {mask}) != {mask}) return stop(cpu, Stop::undefined_state);"]
        if mode in (2, 5):
            statements.append(f"if (!cpu.a_known[{source}]) return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{source}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(f"std::uint32_t source_value = 0; if (!read_operand(cpu, bus, {address}, {size}u, source_value)) return false;")
        statements.append(f"const std::uint32_t result = (cpu.d[{destination}] | source_value) & {mask};")
        statements.append(f"cpu.d[{destination}] = (cpu.d[{destination}] & ~{mask}) | result; cpu.d_known[{destination}] |= {mask};")
        statements += [f"logical_flags(cpu, (result & {sign}) != 0, result == 0);", done]
        return " ".join(statements)
    if op == "cmp_memory_to_d":
        size, mode, source, displacement, destination = args
        mask = _u((1 << (size * 8)) - 1)
        statements = [
            f"if ((cpu.d_known[{destination}] & {mask}) != {mask}) "
            f"return stop(cpu, Stop::undefined_state);"]
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{source}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{source}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(
            f"std::uint32_t source_value = 0; if (!read_operand(cpu, bus, "
            f"{address}, {size}u, source_value)) return false;")
        statements.append(
            f"return compare_immediate(cpu, {size}u, "
            f"cpu.d[{destination}] & {mask}, source_value, {next_pc});")
        return " ".join(statements)
    if op == "addq_d":
        size, dest, immediate = args
        return (f"return add_quick_data(cpu, {size}u, {dest}u, {immediate}u, "
                f"{next_pc});")
    if op == "addq_memory":
        size, mode, reg, displacement, immediate = args
        if mode in (2, 5):
            prefix = (f"if (!cpu.a_known[{reg}]) "
                      f"return stop(cpu, Stop::undefined_state); ")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            prefix, address = "", _u(displacement)
        return (prefix + f"return add_quick_memory(cpu, bus, {address}, "
                f"{size}u, {immediate}u, {next_pc});")
    if op == "subq_d":
        size, dest, immediate = args
        return (f"return subtract_quick_data(cpu, {size}u, {dest}u, "
                f"{immediate}u, {next_pc});")
    if op == "subq_memory":
        size, mode, reg, displacement, immediate = args
        statements = []
        if mode in (2, 5):
            statements.append(
                f"if (!cpu.a_known[{reg}]) "
                f"return stop(cpu, Stop::undefined_state);")
            address = f"cpu.a[{reg}] + {_u(displacement)}"
        else:
            address = _u(displacement)
        statements.append(
            f"return subtract_quick_memory(cpu, bus, {address}, {size}u, "
            f"{immediate}u, {next_pc});")
        return " ".join(statements)
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
    if op == "clr_memory_indexed":
        size, base, extension = args
        return (f"std::uint32_t address = 0; if (!indexed_address(cpu, {base}u, "
                f"{extension}u, address)) return false; "
                f"if (!clear_memory(cpu, bus, address, {size}u)) return false; "
                f"logical_flags(cpu, false, true); {done}")
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


def emit_cpp(image: bytes, entry: int, base: int = 0, limit: int = 4096,
             additional_entries: tuple[int, ...] = ()):
    instructions, limited = discover(image, entry, base, limit, additional_entries)
    unsupported = tuple(i.pc for i in instructions if i.mnemonic in ("unsupported", "invalid_fetch"))
    source = ['#include "m68k_runtime.hpp"', "namespace arcaderecomp_m68k_generated {",
              "using namespace arcaderecomp::m68k;",
              "inline bool step(CPU& cpu, Bus& bus) {",
              "try { bool exception_taken = false;",
              "if (!execution_allowed(cpu, bus, exception_taken)) return false;",
              "if (exception_taken) return true;",
              "(void)bus; switch(cpu.pc) {"]
    for ins in instructions:
        source.append(f"case {_u(ins.pc)}: {{ {_emit(ins)} }}")
    source += ["default: return stop(cpu, Stop::untranslated_pc);", "}",
               "} catch(const BusFault& fault) {",
               "cpu.access_address = fault.address; cpu.access_write = fault.write; cpu.access_width = fault.width;",
               "return stop(cpu, Stop::bus_access);", "}", "}", "}"]
    return "\n".join(source) + "\n", TranslationReport(entry, len(instructions),
        len(instructions) - len(unsupported), unsupported, limited)
