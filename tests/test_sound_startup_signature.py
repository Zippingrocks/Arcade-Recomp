"""ROM-free tests for the bounded sound startup signature proof."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp import sound_startup_signature as proof
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native


def words(*values):
    return b"".join(value.to_bytes(2, "big") for value in values)


SEQUENCE = words(
    0x4284,
    0x0CB8, 0x4572, 0x726F, 0x0C08, 0x660E,
    0x0CB8, 0x7253, 0x6574, 0x0C0C, 0x6604,
    0x1838, 0x0C04, 0x41F8, 0x0000, 0x3C3C, 0x0003,
)
IMAGE = bytes(proof.START - proof.ROM_BASE) + SEQUENCE


class SoundStartupSignatureTests(unittest.TestCase):
    def test_exact_sequence_exhaustively_partitions_all_unknown_bytes(self):
        report = proof.analyze(SEQUENCE, base=proof.START)
        counts = [int(case["assignments"]) for case in report["partition"]]
        self.assertEqual(sum(counts), 2**72)
        self.assertEqual(counts, [(2**32 - 1) * 2**40, (2**32 - 1) * 2**8, 256])
        self.assertEqual(report["convergence"]["architectural_state_classes"], 257)
        self.assertEqual(report["convergence"]["pc"], proof.CONVERGENCE)
        self.assertTrue(report["convergence"]["d4_fully_known_in_every_class"])
        self.assertEqual(report["convergence"]["nzvc"], 0)
        self.assertFalse(report["input_domain"]["initial_values_established"])
        self.assertFalse(report["proof_scope"]["safe_to_replace_unknown_ram_with_zero"])
        self.assertEqual(report["image_sha256"], hashlib.sha256(SEQUENCE).hexdigest())

    def test_every_instruction_semantic_is_guarded(self):
        for offset in range(0, len(SEQUENCE), 2):
            damaged = bytearray(SEQUENCE)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                proof.analyze(bytes(damaged), base=proof.START)

    def test_native_representatives_and_every_preserved_byte_converge(self):
        source, report = emit_cpp(SEQUENCE, proof.START, proof.START)
        self.assertEqual(report.unsupported, (proof.CONVERGENCE,))
        native(source, r'''
#include <array>
using namespace arcaderecomp_m68k_generated;
struct SignatureBus final : Bus {
    std::array<std::uint8_t,16> bytes{}; unsigned reads=0;
    std::uint8_t read8(std::uint32_t address) override {
        ++reads;if(address<0xc04u||address>=0xc14u)throw BusFault(address,false);
        return bytes[address-0xc04u];
    }
    std::uint16_t read16(std::uint32_t address) override {
        ++reads;if(address<0xc04u||address+1u>=0xc14u||address&1u)throw BusFault(address,false,2);
        const unsigned i=address-0xc04u;return static_cast<std::uint16_t>(bytes[i]<<8u|bytes[i+1u]);
    }
    void longword(unsigned address,std::uint32_t value) {
        for(unsigned i=0;i<4;++i)bytes[address-0xc04u+i]=static_cast<std::uint8_t>(value>>(24u-i*8u));
    }
};
static int run(SignatureBus& bus,unsigned expected_d4,unsigned expected_reads) {
    CPU cpu;reset_from_vectors(cpu,0x2000u,0x600172u);
    for(unsigned steps=0;cpu.pc!=0x600194u&&steps<9u;++steps)if(!step(cpu,bus))return 1;
    if(cpu.pc!=0x600194u||cpu.d[4]!=expected_d4||cpu.d_known[4]!=0xffffffffu)return 2;
    if((cpu.sr&0xfu)!=0u||(cpu.sr_known&0xfu)!=0xfu||bus.reads!=expected_reads)return 3;
    return 0;
}
int main() {
    // Representatives exercise zero, signed boundaries and both sides of each
    // equality. The analyzer proves that BNE observes equality only.
    const std::uint32_t mismatches[]={0u,1u,0x4572726eu,0x45727270u,0x7fffffffu,0x80000000u,0xffffffffu};
    for(auto first:mismatches) {SignatureBus bus;bus.longword(0xc08u,first);if(run(bus,0u,2u))return 1;}
    for(auto second:mismatches) {SignatureBus bus;bus.longword(0xc08u,0x4572726fu);bus.longword(0xc0cu,second);if(run(bus,0u,4u))return 2;}
    for(unsigned saved=0;saved<256u;++saved) {
        SignatureBus bus;bus.bytes[0]=static_cast<std::uint8_t>(saved);
        bus.longword(0xc08u,0x4572726fu);bus.longword(0xc0cu,0x72536574u);
        if(run(bus,saved,5u))return 3;
    }
    return 0;
}
''')

    def test_invalid_domains_and_truncation_are_refused(self):
        for image, base in ((b"", proof.START), (b"\0", proof.START),
                            (bytearray(SEQUENCE), proof.START), (SEQUENCE, True),
                            (SEQUENCE, -2), (SEQUENCE, proof.START + 2),
                            (bytes(proof.MAX_IMAGE + 2), proof.START)):
            with self.subTest(image_type=type(image), base=base), self.assertRaises(ValueError):
                proof.analyze(image, base=base)
        with self.assertRaises(ValueError):
            proof.analyze(SEQUENCE[:-2], base=proof.START)

    def test_cli_authenticates_before_analysis_and_emits_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            chip = Path(directory) / "chip"
            output = Path(directory) / "report.json"
            chip.write_bytes(b"synthetic chip")
            identity = {"file": "synthetic", "sha1": "1", "crc32": "2"}
            with patch.object(proof, "authenticate_chip", return_value=(IMAGE, identity)):
                self.assertEqual(proof.main(["--chip", str(chip), "--output", str(output)]), 0)
            report = json.loads(output.read_bytes())
            self.assertEqual(report["chip_identity"], identity)
            self.assertIn("authenticated", report["provenance"])
            self.assertNotIn(b"\r", output.read_bytes())
            for field in ("rom_bytes", "opcodes", "payload", "disassembly"):
                self.assertNotIn(f'"{field}":'.encode(), output.read_bytes())

    def test_cli_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            chip = Path(directory) / "chip"
            output = Path(directory) / "report.json"
            chip.write_bytes(b"wrong")
            output.write_text("old", encoding="utf-8")
            with patch.object(proof, "authenticate_chip", side_effect=ValueError("wrong")), \
                    patch.object(proof, "analyze", side_effect=AssertionError("must not analyze")):
                self.assertEqual(proof.main(["--chip", str(chip), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
