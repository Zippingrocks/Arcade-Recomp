"""Private authenticated original sound-ROM AOT bootstrap, never a board boot.

Generated game C++ and reconstructed bytes are restricted to this checkout's
ignored build directory. Public tests use generated instructions only.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arcaderecomp.m68k_cpp import emit_cpp
from arcaderecomp.roms import load_layout, reconstruct


HARNESS = r'''
#include "m68k_sound_bus.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
int main(int argc, char** argv) {
    if (argc != 7 || (std::string(argv[2]) != "0" && std::string(argv[2]) != "1") ||
            (std::string(argv[3]) != "0" && std::string(argv[3]) != "1") ||
            (std::string(argv[4]) != "0" && std::string(argv[4]) != "1") ||
            (std::string(argv[5]) != "0" && std::string(argv[5]) != "1") ||
            (std::string(argv[6]) != "0" && std::string(argv[6]) != "1")) return 2;
    std::ifstream file(argv[1], std::ios::binary);
    if (!file) return 3;
    std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(file)), {});
    if (image.size() != 0x80000u) return 4;
    auto be32 = [&](unsigned offset) {
        return (std::uint32_t(image[offset]) << 24) | (std::uint32_t(image[offset+1]) << 16) |
               (std::uint32_t(image[offset+2]) << 8) | image[offset+3];
    };
    using namespace arcaderecomp_m68k_generated;
    CPU cpu;
    if (!reset_from_vectors(cpu, be32(0), be32(4))) return 5;
    SoundROMBus bus(std::move(image));
    bus.enable_common_control_research(std::string(argv[2]) == "1");
    bus.enable_hotd_sound_control_research(std::string(argv[3]) == "1");
    bus.enable_sound_ram_research(std::string(argv[4]) == "1");
    bus.enable_slot_mixer_research(std::string(argv[5]) == "1");
    bus.enable_dsp_registers_research(std::string(argv[6]) == "1");
    while (cpu.completed < 100000u && step(cpu, bus)) {}
    std::cout << "{\"completed_instructions\":" << cpu.completed
      << ",\"pc\":" << cpu.pc << ",\"sr\":" << cpu.sr
      << ",\"ssp\":" << cpu.a[7] << ",\"a5\":" << cpu.a[5]
      << ",\"stop_code\":" << static_cast<unsigned>(cpu.stop)
      << ",\"denied_address\":" << cpu.access_address
      << ",\"denied_width\":" << unsigned(cpu.access_width)
      << ",\"denied_write\":" << (cpu.access_write ? "true" : "false")
      << ",\"scsp_discarded_reads\":" << bus.common_control().completed_discarded_reads()
      << ",\"scsp_control_writes\":" << bus.common_control().completed_writes()
      << ",\"scsp_written_fields\":" << bus.common_control().written_fields()
      << ",\"scsp_written_known_mask\":" << bus.common_control().written_known_mask()
      << ",\"scsp_dsp_memory_writes\":" << bus.dsp_memory_control().completed_writes()
      << ",\"scsp_dsp_memory_fields\":" << bus.dsp_memory_control().written_fields()
      << ",\"scsp_dsp_memory_known_mask\":" << bus.dsp_memory_control().written_known_mask()
      << ",\"sound_control_writes\":" << bus.hotd_sound_control().completed_writes()
      << ",\"sound_control_last_data\":" << bus.hotd_sound_control().last_transaction_data()
      << ",\"sound_control_last_known_mask\":" << bus.hotd_sound_control().last_transaction_known_mask()
      << ",\"sound_ram_known_bytes\":" << bus.sound_ram().known_bytes()
      << ",\"slot_mixer_discarded_reads\":" << bus.slot_mixer_control().completed_discarded_reads()
      << ",\"slot_mixer_writes\":" << bus.slot_mixer_control().completed_writes()
      << "}\n";
    return cpu.stop == Stop::none ? 6 : 0;
}
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build" / "m68k-sound-bootstrap")
    parser.add_argument("--compiler", default=shutil.which("g++") or shutil.which("clang++"))
    parser.add_argument("--scsp-common-controls", action="store_true",
                        help="Opt in to documented SCSP common-control transactions; not sound or reset timing")
    parser.add_argument("--hotd-sound-control", action="store_true",
                        help="Accept the bounded original-HOTD Model 2 sound-control write contract")
    parser.add_argument("--sound-ram", action="store_true",
                        help="Enable 512 KiB sound RAM with unknown initial byte values")
    parser.add_argument("--scsp-slot-mixers", action="store_true",
                        help="Enable documented per-slot mixer word transactions")
    parser.add_argument("--scsp-dsp-registers", action="store_true",
                        help="Enable documented DSP COEF and MADRS register files")
    args = parser.parse_args(argv)
    if not args.compiler:
        parser.error("A C++17 g++/clang++ compiler is required")
    output = args.work_dir.resolve()
    build_root = ROOT / "build"
    if (build_root.resolve() != build_root or not output.is_relative_to(build_root)
            or output == build_root):
        parser.error("Private generated output must be in a subdirectory of this checkout's ignored build/")
    region = next(r for r in load_layout(ROOT / "targets/hotd1/original.json")["regions"]
                  if r["name"] == "audiocpu")
    spec = region["loads"][0]
    chip = args.chip.read_bytes()
    sha1 = hashlib.sha1(chip).hexdigest()
    if (len(chip) != int(spec["size"], 0) or sha1 != spec["sha1"] or
            f"{zlib.crc32(chip) & 0xffffffff:08x}" != spec["crc32"]):
        parser.error("Input is not the authenticated original HOTD1 sound chip")
    image = reconstruct(region, {spec["file"]: chip})
    entry = int.from_bytes(image[4:8], "big")
    source, report = emit_cpp(image, entry, base=0x600000)
    output.mkdir(parents=True, exist_ok=True)
    # Never overwrite prior private artifacts or follow a pre-existing file
    # alias to the evidence input. Retain each generated run for inspection.
    output = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    cpp, binary, image_path = output / "private_sound.cpp", output / "private_sound_probe", output / "audiocpu.bin"
    cpp.write_text(source + HARNESS, encoding="utf-8")
    image_path.write_bytes(image)
    subprocess.run([args.compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                    str(cpp), "-o", str(binary)], check=True, timeout=60)
    result = subprocess.run([str(binary), str(image_path), str(int(args.scsp_common_controls)),
                             str(int(args.hotd_sound_control)), str(int(args.sound_ram)),
                             str(int(args.scsp_slot_mixers)), str(int(args.scsp_dsp_registers))],
                            check=True, capture_output=True,
                            text=True, timeout=30)
    print(json.dumps({"schema": "hotdo-sound-aot-bootstrap-v1", "chip_sha1": sha1,
                      "proof": "original-byte architecture-subset; explicit vector input; not cabinet reset",
                      "scsp_common_control_research": args.scsp_common_controls,
                      "hotd_sound_control_research": args.hotd_sound_control,
                      "sound_ram_research": args.sound_ram,
                      "scsp_slot_mixers_research": args.scsp_slot_mixers,
                      "scsp_dsp_registers_research": args.scsp_dsp_registers,
                      "translation": asdict(report), "execution": json.loads(result.stdout)}, indent=2))


if __name__ == "__main__":
    main()
