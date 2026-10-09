"""ArcadeRecomp preflight tools; this is not yet an arcade CPU recompiler."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from .roms import RomError, load_layout, reconstruct, select_regions, verify
from .i960 import decode, read_boot_record
from .i960_cpp import emit_cpp


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify and map original arcade ROMs")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("audit", "build", "inspect", "translate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--layout", type=Path, required=True)
        cmd.add_argument("--rom", type=Path, required=True)
        cmd.add_argument("--parent", type=Path, help="Optional separate parent ZIP for split MAME ROM sets")
        cmd.add_argument("--region", action="append", help="Only check/rebuild the named memory region")
        if name == "build":
            cmd.add_argument("--output", type=Path, required=True)
        if name == "inspect":
            cmd.add_argument("--count", type=int, default=32, help="Maximum sequential i960 instructions")
        if name == "translate":
            cmd.add_argument("--output", type=Path, required=True, help="Generated C++ (must stay private)")
            cmd.add_argument("--limit", type=int, default=512, help="CFG discovery instruction cap")
    args = parser.parse_args(argv)
    try:
        layout = load_layout(args.layout)
        regions = select_regions(layout, ["maincpu"] if args.action in ("inspect", "translate") else args.region)
        archives = [args.rom] + ([args.parent] if args.parent else [])
        report, matches = verify(archives, regions)
        print(json.dumps({"rom_set": layout["rom_set"], **report}, indent=2))
        if not report["ok"]:
            print("REFUSED: supplied ROMs do not match this revision.", file=sys.stderr)
            return 2
        if args.action == "build":
            images = {region["name"]: reconstruct(region, matches) for region in regions}
            args.output.mkdir(parents=True, exist_ok=True)
            for name, content in images.items():
                target = args.output / (name + ".bin")
                target.write_bytes(content)
                print(f"Wrote {target}: sha256={hashlib.sha256(content).hexdigest()}")
            print("Research-only game-derived region files; do not distribute.")
        if args.action in ("inspect", "translate"):
            image = reconstruct(regions[0], matches)
            boot = read_boot_record(image)
            print("Original ROM i960 boot record: " + json.dumps(boot, sort_keys=True))
            if args.action == "inspect":
                if not 1 <= args.count <= 10000:
                    raise RomError("--count must be between 1 and 10000")
                pc = boot["initial_ip"]
                for _ in range(args.count):
                    ins = decode(image, pc)
                    print(f"0x{ins.pc:08x}  {ins.asm()}")
                    if ins.issue or ins.flow in ("return", "jump", "indirect", "fault", "unknown"):
                        break
                    pc = ins.next_pc
            else:
                source, detail = emit_cpp(image, boot["initial_ip"], args.limit)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(source, encoding="utf-8")
                print(json.dumps({"discovered": detail.discovered,
                                  "translated": detail.translated,
                                  "unsupported_count": len(detail.unsupported),
                                  "unsupported_ips": [f"0x{x:08x}" for x in detail.unsupported[:20]],
                                  "limit_reached": detail.limit_reached}, indent=2))
                print("PRIVATE ROM-derived C++ output: do not publish or commit.")
        return 0
    except (RomError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
