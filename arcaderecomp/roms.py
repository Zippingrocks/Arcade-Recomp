"""Independent ROM identification and memory layout reconstruction utilities.

Manifests contain publicly documented chip fingerprints, never game bytes.
"""
import hashlib
import json
from pathlib import Path
import zipfile
import zlib


class RomError(ValueError):
    pass


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def load_layout(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not data.get("regions"):
        raise RomError("Missing or unsupported ROM layout")
    return data


def select_regions(layout, names=None):
    if not names:
        return layout["regions"]
    result = [r for r in layout["regions"] if r["name"] in names]
    if {r["name"] for r in result} != set(names):
        raise RomError("Unknown region requested")
    return result


def verify(archive_paths, regions):
    """Find exact SHA-1 + CRC32 chip matches in standalone or split MAME ZIPs."""
    expected = {item["file"]: item
                for region in regions for item in region["loads"]}
    matches = {}
    candidates = {name: [] for name in expected}
    for path in archive_paths:
        path = Path(path)
        if path.suffix.lower() == ".7z":
            from .archive7z import read_7z_members
            for name, (member, content) in read_7z_members(path, set(expected)).items():
                item = expected[name]
                if (len(content) == number(item["size"])
                        and f"{zlib.crc32(content) & 0xffffffff:08x}" == item["crc32"].lower()
                        and hashlib.sha1(content).hexdigest() == item["sha1"].lower()):
                    matches[name] = content
                else:
                    candidates[name].append(f"{path.name}:{member}")
            continue
        if path.suffix.lower() != ".zip":
            raise RomError("Unsupported archive extension (expected .zip or .7z)")
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                name = entry.filename.replace("\\", "/").split("/")[-1]
                if name not in expected:
                    continue
                if entry.file_size > 128 * 1024 * 1024:
                    raise RomError("Suspiciously large ROM member")
                content = archive.read(entry)
                item = expected[name]
                if (len(content) == number(item["size"])
                        and f"{zlib.crc32(content) & 0xffffffff:08x}" == item["crc32"].lower()
                        and hashlib.sha1(content).hexdigest() == item["sha1"].lower()):
                    matches[name] = content
                else:
                    candidates[name].append(f"{path.name}:{entry.filename}")
    missing = [name for name in expected if name not in matches]
    return {"ok": not missing, "matched": len(matches),
            "total": len(expected), "unmatched": sorted(missing),
            "mismatching_locations": {k: v for k, v in candidates.items()
                                     if k in missing and v}}, matches


def reconstruct(region, matches):
    """Deterministic research region, not proof of uninitialized board state."""
    size = number(region["size"])
    if not 0 < size <= 256 * 1024 * 1024:
        raise RomError("Region exceeds size limit")
    memory = bytearray(size)
    used = bytearray(size)
    for spec in region["loads"]:
        data = matches[spec["file"]]
        if spec.get("swap16"):
            data = bytes(b for a, b in zip(data[1::2], data[::2]) for b in (a, b))
        group = number(spec.get("group", 1))
        stride = number(spec.get("stride", group))
        offset = number(spec["offset"])
        if not 0 < group <= stride <= 32 or len(data) % group:
            raise RomError("Invalid ROM wiring")
        if offset + (len(data) // group - 1) * stride + group > size:
            raise RomError("ROM load out of bounds")
        for lane in range(group):
            segment = data[lane::group]
            start = offset + lane
            stop = start + len(segment) * stride
            if any(used[start:stop:stride]):
                raise RomError("Overlapping ROM chips")
            memory[start:stop:stride] = segment
            used[start:stop:stride] = b"\x01" * len(segment)
    for mapping in region.get("copies", []):
        src, dst, length = map(number, (mapping["source"], mapping["target"], mapping["size"]))
        if src + length > size or dst + length > size or not all(used[src:src + length]):
            raise RomError("Invalid memory mirror")
        if any(used[dst:dst + length]):
            raise RomError("Overlapping memory mirror")
        memory[dst:dst + length] = memory[src:src + length]
        used[dst:dst + length] = b"\x01" * length
    return bytes(memory)
