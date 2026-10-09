"""Conservative ahead-of-time C++ emission for selected Intel i960 instructions.

This is a research translator, not a functional Model 2C game runtime.
The generated C++ compiles fixed, decoded instruction semantics. It does not
decode 32-bit i960 instructions during native execution. Unsupported cases
become deliberate stop sites, never silently translated as NOPs.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i960 import Instruction, decode, discover


@dataclass(frozen=True)
class TranslationReport:
    entry: int
    discovered: int
    translated: int
    unsupported: tuple[int, ...]
    limit_reached: bool


def _operand(raw: int, literal: bool) -> str:
    return f"{raw}u" if literal else f"cpu.r[{raw}]"


def _addr(ins: Instruction, word: int, image: bytes) -> str:
    base = (word >> 14) & 31
    if not word & 0x1000:  # MEMA
        offset = word & 0xfff
        return f"(cpu.r[{base}] + {offset}u)" if word & 0x2000 else f"{offset}u"
    mode = (word >> 10) & 15
    scale = (word >> 7) & 7
    index = word & 31
    disp = int.from_bytes(image[ins.pc + 4:ins.pc + 8], "little") if ins.size == 8 else 0
    idx = f"(cpu.r[{index}] << {scale})"
    if mode == 4:
        return f"cpu.r[{base}]"
    if mode == 5:
        return f"({ins.pc + 8}u + {disp}u)"
    if mode == 7:
        return f"(cpu.r[{base}] + {idx})"
    if mode == 12:
        return f"{disp}u"
    if mode == 13:
        return f"(cpu.r[{base}] + {disp}u)"
    if mode == 14:
        return f"({idx} + {disp}u)"
    if mode == 15:
        return f"(cpu.r[{base}] + {idx} + {disp}u)"
    raise ValueError("Unsupported memory address mode")


def _emit_op(ins: Instruction, image: bytes) -> str | None:
    """Return generated C++ statement or None for unsupported semantics."""
    if ins.issue:
        return None
    op = ins.mnemonic
    word = ins.word
    target = f"0x{ins.target:08x}u" if ins.target is not None else None
    if ins.form in ("MEMA", "MEMB") and op == "callx":
        return f"return frame_call(cpu, bus, {_addr(ins, word, image)}, 0x{ins.next_pc:08x}u);"

    if ins.form in ("MEMA", "MEMB") and op in ("lda", "ld", "st"):
        address = _addr(ins, word, image)
        dest = (word >> 19) & 31
        if op == "lda":
            return f"cpu.r[{dest}] = {address};"
        if op == "ld":
            return f"if (!bus.read32) return stop(cpu); cpu.r[{dest}] = bus.read32(bus.ctx, {address});"
        return f"if (!bus.write32) return stop(cpu); bus.write32(bus.ctx, {address}, cpu.r[{dest}]);"

    if ins.form == "REG":
        # Special function registers and the full i960 local-register frame
        # model have not been implemented in this tranche.
        if word & (0x20 | 0x40):
            return None
        # The destination-mode field is irrelevant for compare-only REG
        # instructions. Some legitimate ROM instructions set it.
        if word & 0x2000 and op not in ("cmpo", "cmpi"):
            return None
        a = _operand(word & 31, bool(word & 0x800))
        b = _operand((word >> 14) & 31, bool(word & 0x1000))
        dst = (word >> 19) & 31
        if op in ("addo", "subo"):
            symbol = "+" if op == "addo" else "-"
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({b} {symbol} {a});"
        if op == "mov":
            return f"cpu.r[{dst}] = {a};"
        if op in ("shlo", "shro"):
            symbol = "<<" if op == "shlo" else ">>"
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({b} {symbol} ({a} & 31u));"
        if op in ("cmpo", "cmpi"):
            # Toggling bit 31 provides portable two's-complement signed order.
            left = f"({b} ^ 0x80000000u)" if op == "cmpi" else b
            right = f"({a} ^ 0x80000000u)" if op == "cmpi" else a
            return f"cpu.cc = ({left} < {right}) ? -1 : ({left} > {right}) ? 1 : 0;"
        return None

    if ins.form == "COBR" and op in ("cmpibne", "cmpibe", "cmpobne", "cmpobe"):
        # The compare-branch's first source is either immediate 0..31 or reg.
        # This tranche rejects its special-function-register variant.
        if word & 1:
            return None
        a = _operand((word >> 19) & 31, bool(word & 0x2000))
        b = f"cpu.r[{(word >> 14) & 31}]"
        predicate = "!=" if op.endswith("ne") else "=="
        # i960 compare-and-branch also updates the arithmetic condition code.
        left = f"({b} ^ 0x80000000u)" if op.startswith("cmpib") else b
        right = f"({a} ^ 0x80000000u)" if op.startswith("cmpib") else a
        return (f"cpu.cc = ({left} < {right}) ? -1 : ({left} > {right}) ? 1 : 0; "
                f"if ({b} {predicate} {a}) {{ cpu.ip = {target}; return true; }}")

    if ins.form == "CTRL":
        if op == "call":
            return f"return frame_call(cpu, bus, {target}, 0x{ins.next_pc:08x}u);"
        if op == "ret":
            return "return frame_return(cpu, bus);"
        if op == "b":
            return f"cpu.ip = {target}; return true;"
        condition = {
            "bl": "cpu.cc < 0", "ble": "cpu.cc <= 0",
            "bg": "cpu.cc > 0", "bge": "cpu.cc >= 0",
            "be": "cpu.cc == 0", "bne": "cpu.cc != 0",
        }.get(op)
        if condition is not None:
            return f"if ({condition}) {{ cpu.ip = {target}; return true; }}"
        return None

    return None


def emit_cpp(image: bytes, entry: int, max_instructions: int = 256) -> tuple[str, TranslationReport]:
    """Translate reachable, ROM-resident instructions into a native C++ stepper.

    Memory is supplied through explicit device/bus callbacks. Local CALL,
    CALLX and RET are modeled with four cached register frames. Supervisor/fault
    returns, interrupt frames, exact cycles and unimplemented opcodes stop safely. The generated source is game-derived; keep it out of Git.
    """
    graph = discover(image, entry, limit=max_instructions)
    translated = 0
    unsupported = []
    bodies = []
    for pc, ins in sorted(graph["instructions"].items()):
        body = _emit_op(ins, image)
        if body is None:
            unsupported.append(pc)
            body = "return stop(cpu);"
        else:
            translated += 1
            if body.startswith("return frame_"):
                pass  # CALL/RET helper sets the next IP itself
            elif body.startswith("if (") and "return true;" in body and body.endswith("}"):
                body += f" cpu.ip = 0x{ins.next_pc:08x}u; return true;"
            elif not (body.endswith("return true;") or body.endswith("return stop(cpu);")):
                body += f" cpu.ip = 0x{ins.next_pc:08x}u; return true;"
        bodies.append(f"      case 0x{pc:08x}u: {{ {body} }}")
    result = """// GENERATED — private ROM-derived translation output; do not redistribute.
// Original source and opcode bytes are NOT embedded. Only translated operations.
#include <cstdint>
#include "i960_frame_runtime.hpp"

namespace arcaderecomp_generated {
static inline bool step(CPU& cpu, const Bus& bus) {
    switch (cpu.ip) {
""" + "\n".join(bodies) + """
      default: return stop(cpu);
    }
}
} // namespace arcaderecomp_generated
"""
    report = TranslationReport(entry, len(graph["instructions"]), translated,
                               tuple(unsupported), graph["limit_reached"])
    return result, report
