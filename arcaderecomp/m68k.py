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
    if op == 0x4e75:
        return Instruction(pc, 2, "rts")
    if op == 0x46fc:
        return Instruction(pc, 4, "move_to_sr", (word(2),))
    if op & 0xf100 == 0x7000:
        return Instruction(pc, 2, "moveq", ((op >> 9) & 7, _signed(op & 255, 8)))
    if (op & 0xff00 in (0x0000, 0x0200, 0x0a00) and
            ((op >> 6) & 3) != 3 and (op >> 3) & 7 == 0):
        # Immediate logic to Dn only; memory and CCR/SR forms stay unsupported.
        size = (1, 2, 4)[(op >> 6) & 3]
        immediate, length = word(2), 4
        if size == 4:
            immediate, length = immediate << 16 | word(4), 6
        immediate &= (1 << (size * 8)) - 1
        kind = {0x0000: 0, 0x0200: 1, 0x0a00: 2}[op & 0xff00]
        return Instruction(pc, length, "logic_immediate_d", (size, kind, op & 7, immediate))
    if op & 0xff00 == 0x0c00 and ((op >> 6) & 3) != 3:
        size, mode, reg = (1, 2, 4)[(op >> 6) & 3], (op >> 3) & 7, op & 7
        # Non-updating destinations only. CMPI PC-relative is NOT MC68000.
        if mode in (0, 2, 5) or (mode == 7 and reg in (0, 1)):
            immediate, length = word(2), 4
            if size == 4:
                immediate, length = immediate << 16 | word(4), 6
            immediate &= (1 << (size * 8)) - 1
            displacement = 0
            if mode == 5 or (mode, reg) == (7, 0):
                displacement = _signed(word(length), 16)
                length += 2
            elif (mode, reg) == (7, 1):
                displacement = word(length) << 16 | word(length + 2)
                length += 4
            return Instruction(pc, length, "cmpi", (size, immediate, mode, reg, displacement))
    if op & 0xff00 == 0x4200 and ((op >> 6) & 3) != 3:
        size, mode, reg = (1, 2, 4)[(op >> 6) & 3], (op >> 3) & 7, op & 7
        if mode == 0:
            return Instruction(pc, 2, "clr_d", (size, reg))
        if mode in (2, 3, 5) or (mode == 7 and reg in (0, 1)):
            displacement, length = 0, 2
            if mode == 5 or (mode, reg) == (7, 0):
                displacement, length = _signed(word(2), 16), 4
            elif (mode, reg) == (7, 1):
                displacement, length = word(2) << 16 | word(4), 6
            return Instruction(pc, length, "clr_memory", (size, mode, reg, displacement))
    if op & 0xf1c0 in (0x2040, 0x3040):
        size, mode, reg, dest = (2 if op & 0x1000 else 4), (op >> 3) & 7, op & 7, (op >> 9) & 7
        if mode in (0, 1, 2):
            return Instruction(pc, 2, "movea", (size, mode, reg, dest, 0))
        if mode == 5:
            return Instruction(pc, 4, "movea", (size, mode, reg, dest,
                                                _signed(word(2), 16)))
        if mode == 7 and reg == 0:
            return Instruction(pc, 4, "movea", (size, mode, reg, dest,
                                                _signed(word(2), 16)))
        if mode == 7 and reg == 1:
            return Instruction(pc, 6, "movea", (size, mode, reg, dest,
                                                word(2) << 16 | word(4)))
        if mode == 7 and reg == 4:
            value, length = word(2), 4
            if size == 4:
                value, length = value << 16 | word(4), 6
            return Instruction(pc, length, "movea", (size, mode, reg, dest,
                                                      value))
    if op >> 12 in (1, 2, 3):
        size = {1: 1, 2: 4, 3: 2}[op >> 12]
        src_mode, src_reg = (op >> 3) & 7, op & 7
        dst_mode, dst_reg = (op >> 6) & 7, (op >> 9) & 7
        if size in (2, 4) and src_mode == 1 and dst_mode == 0:
            return Instruction(pc, 2, "move_address_to_d",
                               (size, src_reg, dst_reg))
        if src_mode == 3 and dst_mode == 3:
            return Instruction(pc, 2, "move_memory_postincrement",
                               (size, src_reg, dst_reg))
        if dst_mode == 0 and (src_mode in (2, 3, 5) or
                              (src_mode == 7 and src_reg in (0, 1))):
            # Memory-source MOVE, without address-register updates or indexing.
            displacement, length = 0, 2
            if src_mode == 5 or (src_mode, src_reg) == (7, 0):
                displacement, length = _signed(word(2), 16), 4
            elif (src_mode, src_reg) == (7, 1):
                displacement, length = word(2) << 16 | word(4), 6
            return Instruction(pc, length, "move_memory_to_d",
                               (size, src_mode, src_reg, displacement, dst_reg))
        if ((src_mode == 0 or (src_mode, src_reg) == (7, 4)) and
                (dst_mode == 0 or (size != 4 and
                 (dst_mode == 5 or (dst_mode == 7 and dst_reg in (0, 1)))))):
            length = 2
            if src_mode == 0:
                source_kind, source = 0, src_reg
            else:
                source_kind, source = 1, word(length)
                length += 2
                if size == 4:
                    source = source << 16 | word(length)
                    length += 2
                source &= (1 << (size * 8)) - 1
            displacement = 0
            if dst_mode == 5 or (dst_mode, dst_reg) == (7, 0):
                displacement = _signed(word(length), 16)
                length += 2
            elif (dst_mode, dst_reg) == (7, 1):
                displacement = word(length) << 16 | word(length + 2)
                length += 4
            return Instruction(pc, length, "move", (size, source_kind, source,
                                                    dst_mode, dst_reg, displacement))
    if (op & 0xf020 == 0xe000 and ((op >> 6) & 3) != 3 and
            ((op >> 3) & 3) in (1, 3)):
        size = (1, 2, 4)[(op >> 6) & 3]
        return Instruction(pc, 2, "shift_immediate", (size, op & 7,
                           ((op >> 9) & 7) or 8, (op >> 8) & 1, (op >> 3) & 3))
    if op & 0xf1ff == 0x41f8:
        return Instruction(pc, 4, "lea_absolute", ((op >> 9) & 7, _signed(word(2), 16)))
    if op & 0xf1ff == 0x41f9:
        return Instruction(pc, 6, "lea_absolute", ((op >> 9) & 7, word(2) << 16 | word(4)))
    if op & 0xf1f8 == 0x41e8:
        return Instruction(pc, 4, "lea_displacement",
                           (op & 7, (op >> 9) & 7, _signed(word(2), 16)))
    if op & 0xf1f8 in (0xd0c0, 0xd1c0):
        return Instruction(pc, 2, "adda_d",
                           (4 if op & 0x0100 else 2, op & 7,
                            (op >> 9) & 7))
    if op & 0xf1f8 in (0x9000, 0x9040, 0x9080):
        return Instruction(pc, 2, "sub_d",
                           ((1, 2, 4)[(op >> 6) & 3], op & 7,
                            (op >> 9) & 7))
    if (op & 0xf100 == 0x5000 and ((op >> 6) & 3) != 3 and
            (op >> 3) & 7 == 0):
        size = (1, 2, 4)[(op >> 6) & 3]
        return Instruction(pc, 2, "addq_d",
                           (size, op & 7, ((op >> 9) & 7) or 8))
    if op & 0xf0f8 == 0x50c8:
        displacement = _signed(word(2), 16)
        return Instruction(pc, 4, "dbcc", ((op >> 8) & 15, op & 7),
                           (pc + 2 + displacement) & 0xffffffff)
    if op & 0xf000 == 0x6000:
        displacement, size = _signed(op & 255, 8), 2
        if not op & 255:
            displacement, size = _signed(word(2), 16), 4
        # 0xff is -1 on MC68000; it is NOT a 68020 long displacement marker.
        cc = (op >> 8) & 15
        return Instruction(pc, size, "bsr" if cc == 1 else "bcc", () if cc == 1 else (cc,),
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
        if ins.mnemonic in ("unsupported", "rts"):
            continue
        if ins.target is not None:
            pending.append(ins.target)
        # BSR discovers the callee and the possible continuation. RTS uses the
        # actual bus-supplied return address at run time, never guessed flow.
        if ins.mnemonic != "bcc" or ins.operands[0] != 0:
            pending.append(ins.next_pc)
    return tuple(found[k] for k in sorted(found)), bool(pending)
