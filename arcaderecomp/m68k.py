"""Independent MC68000 bootstrap decoder; no later 680x0 extensions.

Only the documented subset below is accepted. Unsupported instructions are
terminal sites, never guessed instruction lengths for linear disassembly.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Instruction:
    pc: int
    size: int
    mnemonic: str
    operands: tuple[int, ...] = ()
    target: int | None = None

    @property
    def next_pc(self):
        return (self.pc + self.size) & 0xffffffff


def _signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def decode(image: bytes, pc: int, base: int = 0) -> Instruction:
    """Decode one big-endian instruction at an explicit virtual address."""
    if not 0 <= base <= 0xffffffff or base + len(image) > 0x100000000:
        raise ValueError("Image exceeds the 32-bit address range")
    if not 0 <= pc <= 0xffffffff or pc & 1:
        raise ValueError("MC68000 instruction address must be even and 32-bit")
    offset = pc - base

    def word(relative=0):
        start = offset + relative
        if start < 0 or start + 2 > len(image):
            raise ValueError("Truncated or out-of-image MC68000 instruction")
        return int.from_bytes(image[start:start + 2], "big")

    op = word()
    if op == 0x4e71:
        return Instruction(pc, 2, "nop")
    if op == 0x46fc:
        return Instruction(pc, 4, "move_to_sr", (word(2),))
    if op & 0xf100 == 0x7000:
        return Instruction(pc, 2, "moveq", ((op >> 9) & 7, _signed(op & 255, 8)))
    if op & 0xff00 == 0x4200 and ((op >> 6) & 3) != 3:
        size, mode, reg = (1, 2, 4)[(op >> 6) & 3], (op >> 3) & 7, op & 7
        if mode == 0:
            return Instruction(pc, 2, "clr_d", (size, reg))
        if mode == 5 and size == 1:
            return Instruction(pc, 4, "clr_byte_displacement", (reg, _signed(word(2), 16)))
    if op & 0xf1f8 in (0x2040, 0x3040):
        return Instruction(pc, 2, "movea_d", (2 if op & 0x1000 else 4, op & 7, (op >> 9) & 7))
    if op & 0xf1ff == 0x41f9:
        return Instruction(pc, 6, "lea_absolute", ((op >> 9) & 7, word(2) << 16 | word(4)))
    if op & 0xf0f8 == 0x50c8:
        displacement = _signed(word(2), 16)
        return Instruction(pc, 4, "dbcc", ((op >> 8) & 15, op & 7),
                           (pc + 2 + displacement) & 0xffffffff)
    if op & 0xf000 == 0x6000 and (op >> 8) & 15 != 1:  # BSR is not supported.
        displacement, size = _signed(op & 255, 8), 2
        if not op & 255:
            displacement, size = _signed(word(2), 16), 4
        # 0xff is -1 on MC68000; it is NOT a 68020 long displacement marker.
        return Instruction(pc, size, "bcc", ((op >> 8) & 15,),
                           (pc + 2 + displacement) & 0xffffffff)
    return Instruction(pc, 2, "unsupported")


def discover(image: bytes, entry: int, base: int = 0, limit: int = 4096):
    """Follow only supported direct control flow, stopping at unknown sites."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100000:
        raise ValueError("Instruction limit must be 1..100000")
    if not 0 <= base <= 0xffffffff or base + len(image) > 0x100000000:
        raise ValueError("Image exceeds the 32-bit address range")
    if not 0 <= entry <= 0xffffffff:
        raise ValueError("Entry exceeds the 32-bit address range")
    pending, found = [entry], {}
    while pending and len(found) < limit:
        pc = pending.pop()
        if pc in found:
            continue
        try:
            ins = decode(image, pc, base)
        except ValueError:
            found[pc] = Instruction(pc, 0, "invalid_fetch")
            continue
        found[pc] = ins
        if ins.mnemonic == "unsupported":
            continue
        if ins.target is not None:
            pending.append(ins.target)
        if ins.mnemonic != "bcc" or ins.operands[0] != 0:
            pending.append(ins.next_pc)
    return tuple(found[k] for k in sorted(found)), bool(pending)
