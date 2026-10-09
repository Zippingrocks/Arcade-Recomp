"""ArcadeRecomp preflight tools; this is not yet an arcade CPU recompiler."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from .roms import RomError, load_layout, reconstruct, select_regions, verify


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify and map original arcade ROMs")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("audit", "build"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--layout", type=Path, required=True)
        cmd.add_argument("--rom", type=Path, required=True)
        cmd.add_argument("--parent", type=Path, help="Optional separate parent ZIP for split MAME ROM sets")
        cmd.add_argument("--region", action="append", help="Only check/rebuild the named memory region")
        if name == "build":
            cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        layout = load_layout(args.layout)
        regions = select_regions(layout, args.region)
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
        return 0
    except (RomError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
