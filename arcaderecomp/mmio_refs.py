"""Reproducible, metadata-only search for i960 memory-address literals.

A decode-compatible word preceding a literal is NOT proof that code executes.
The optional rooted graph supplies a second, also static, confidence label.
No source bytes or full disassembly are included in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from .i960 import DecodeError, decode, discover


WIDTHS = {
    'ldob': 1, 'ldib': 1, 'stob': 1, 'stib': 1,
    'ldos': 2, 'ldis': 2, 'stos': 2, 'stis': 2,
    'ld': 4, 'st': 4, 'ldl': 8, 'stl': 8,
    'ldt': 12, 'stt': 12, 'ldq': 16, 'stq': 16,
}


def audit_address(image: bytes, address: int, roots: tuple[int, ...] = (),
                  limit: int = 16384, expected_sha256: str | None = None) -> dict:
    """Classify exact aligned literals and immediately preceding MEMB forms."""
    if not 0 <= address <= 0xffffffff:
        raise ValueError('Address must fit an unsigned 32-bit word')
    if not image or len(image) > 64 * 1024 * 1024:
        raise ValueError('Image size must be 1..64 MiB')
    digest = hashlib.sha256(image).hexdigest()
    if expected_sha256 is not None:
        if not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
            raise ValueError('Expected SHA-256 must contain exactly 64 hex digits')
        if digest != expected_sha256.lower():
            raise ValueError('Image SHA-256 does not match the specified baseline')
    for root in roots:
        if root < 0 or root % 4 or root + 4 > len(image):
            raise ValueError('Graph root must be a mapped, word-aligned address')
    graph = discover(image, roots[0], limit, additional_entries=roots[1:]) if roots else None
    selected = graph['instructions'] if graph else {}
    hits = []
    for offset in range(0, len(image) - 3, 4):
        if struct.unpack_from('<I', image, offset)[0] != address:
            continue
        hit = {'literal_offset': f'0x{offset:08x}', 'classification': 'literal_only'}
        if offset >= 4:
            try:
                ins = decode(image, offset - 4)
            except DecodeError:
                ins = None
            if ins and ins.supported and ins.form == 'MEMB' and ins.size == 8:
                mode = (ins.word >> 10) & 15
                hit.update(site=f'0x{ins.pc:08x}', mnemonic=ins.mnemonic,
                           in_selected_graph=ins.pc in selected,
                           register_index=(ins.word >> 19) & 31)
                if mode == 12:
                    if ins.mnemonic == 'lda':
                        hit['classification'] = 'absolute_address_construction'
                    elif ins.mnemonic in WIDTHS:
                        hit['classification'] = 'absolute_memory_operand'
                        hit['access'] = 'write' if ins.mnemonic.startswith('st') else 'read'
                        hit['width_bytes'] = WIDTHS[ins.mnemonic]
                    else:
                        hit['classification'] = 'absolute_control_target'
                else:
                    # The same constant with a base/index is not necessarily
                    # an access to that absolute hardware address.
                    hit['classification'] = 'memory_displacement_only'
        hits.append(hit)
    return {
        'schema_version': 1, 'image_size': len(image), 'image_sha256': digest,
        'target_address': f'0x{address:08x}',
        'roots': [f'0x{x:08x}' for x in roots],
        'graph_limit_reached': graph['limit_reached'] if graph else False,
        'literal_count': len(hits),
        'absolute_memory_operand_count': sum(h['classification'] == 'absolute_memory_operand' for h in hits),
        'hits': hits,
        'evidence_boundary': 'Static candidates, not executed code or a physical device identification.'
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--address', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--root', type=lambda s: int(s, 0), action='append', default=[])
    parser.add_argument('--limit', type=int, default=16384)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.image.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Image exceeds 64 MiB limit')
        result = audit_address(args.image.read_bytes(), args.address, tuple(args.root),
                               args.limit, args.expected_sha256)
        text = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding='utf-8')
        else:
            print(text, end='')
    except (ValueError, OSError) as error:
        parser.exit(2, f'Address audit failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
