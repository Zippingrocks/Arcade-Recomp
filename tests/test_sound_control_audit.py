"""ROM-free sound-control reference classification and evidence preservation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from arcaderecomp import sound_control_audit as audit


def words(*values):
    return b"".join(value.to_bytes(2, "big") for value in values)


class SoundControlAuditTests(unittest.TestCase):
    def test_immediate_and_unknown_register_stores_are_not_execution(self):
        # MOVE.B #7,$400001; MOVE.W D3,$400000; unknown instruction.
        image = words(0x13fc, 7, 0x40, 1, 0x33c3, 0x40, 0, 0xffff)
        report = audit.analyze(image, base=0x1000, entry=0x1000)
        stores = report["store_candidates"]
        self.assertEqual([(s["pc"], s["width"], s["bus_address"]) for s in stores],
                         [(0x1000, 1, 0x400001), (0x1008, 2, 0x400000)])
        self.assertEqual(stores[0]["source"], {"kind": "immediate", "value": 7, "value_known": True})
        self.assertEqual(stores[1]["source"], {"kind": "register", "register": "d3", "value_known": False})
        for store in stores:
            self.assertTrue(store["in_supported_static_graph"])
            self.assertFalse(store["instruction_boundary_verified"])
            self.assertFalse(store["execution_verified"])
            self.assertFalse(store["device_effect_verified"])
        self.assertEqual(report["static_graph"]["stop_sites"], [0x100e])
        self.assertFalse(report["hardware_semantics_verified"])
        self.assertFalse(report["runtime_behavior_changed"])

    def test_data_matches_and_indirect_addresses_do_not_get_promoted(self):
        image = words(0xffff, 0x13c0, 0x40, 1, 0x47f9, 0x40, 0, 0xffff)
        report = audit.analyze(image, base=0, entry=0)
        self.assertEqual(len(report["store_candidates"]), 1)
        self.assertFalse(report["store_candidates"][0]["in_supported_static_graph"])
        self.assertEqual(report["address_materializations"], [{
            "pc": 8, "destination": "a3", "address_value": 0x400000,
            "in_supported_static_graph": False, "instruction_boundary_verified": False}])
        self.assertFalse(report["scan"]["all_references_recovered"])
        self.assertFalse(report["scan"]["indirect_references_resolved"])
        self.assertTrue(report["scan"]["data_may_match_instruction_patterns"])
        self.assertEqual(report["image_sha256"], hashlib.sha256(image).hexdigest())

    def test_physical_bus_masking_and_odd_literal_are_explicit(self):
        # Upper address byte is not on MC68000's 24-bit external bus.
        image = words(0x13c2, 0xab40, 1, 0xffff) + b"\x55\x00\x40\x00\x01\x55"
        report = audit.analyze(image, base=0, entry=0)
        self.assertEqual(report["store_candidates"][0]["bus_address"], 0x400001)
        self.assertEqual(report["aligned_address_values"], [{
            "location": 2, "upper_byte_is_zero": False, "bus_address": 0x400001}])
        self.assertEqual(report["scan"]["examined_offsets"], len(image) // 2)

    def test_nearby_apertures_and_truncated_instructions_are_not_stores(self):
        image = words(0x13c0, 0x40, 2, 0x13c0, 0x3f, 0xfffe, 0xffff, 0x13fc)
        report = audit.analyze(image, base=0, entry=0)
        self.assertEqual(report["store_candidates"], [])
        self.assertEqual(report["address_materializations"], [])

    def test_invalid_domains_and_bounded_candidates(self):
        for image, base, entry in ((b"", 0, 0), (b"\0", 0, 0), (bytearray(2), 0, 0),
                                   (bytes(2), True, 0), (bytes(2), 1, 1),
                                   (bytes(2), -2, 0), (bytes(2), 0, True),
                                   (bytes(2), 0, 2), (bytes(2), 0, -2),
                                   (bytes(4), 0xfffffffe, 0xfffffffe),
                                   (bytes(audit.MAX_IMAGE + 2), 0, 0)):
            with self.assertRaises(ValueError):
                audit.analyze(image, base=base, entry=entry)
        for limit in (False, 0, -1, 100001):
            with self.assertRaises(ValueError):
                audit.analyze(words(0xffff), base=0, entry=0, cfg_limit=limit)
        with patch.object(audit, "MAX_MATCHES", 2), self.assertRaises(ValueError):
            audit.analyze(words(0x40, 1) * 3, base=0, entry=0)

    def test_cfg_limit_does_not_truncate_the_independent_scan(self):
        image = words(0x4e71, 0x13c0, 0x40, 1, 0xffff)
        report = audit.analyze(image, base=0, entry=0, cfg_limit=1)
        self.assertTrue(report["static_graph"]["limit_reached"])
        self.assertEqual(report["static_graph"]["sites"], 1)
        self.assertTrue(report["scan"]["complete_for_declared_patterns"])
        self.assertEqual(len(report["store_candidates"]), 1)
        self.assertFalse(report["store_candidates"][0]["in_supported_static_graph"])

    def test_authentication_uses_size_crc_hash_before_reconstruction(self):
        chip = b"synthetic-chip"
        spec = {"size": hex(len(chip)), "file": "synthetic.bin",
                "sha1": hashlib.sha1(chip).hexdigest(),
                "crc32": f"{zlib.crc32(chip) & 0xffffffff:08x}"}
        region = {"name": "audiocpu", "loads": [spec]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chip"
            path.write_bytes(chip)
            with patch.object(audit, "load_layout", return_value={"regions": [region]}), \
                    patch.object(audit, "reconstruct", return_value=b"image") as reconstruct:
                image, identity = audit.authenticate_chip(path)
                self.assertEqual(image, b"image")
                self.assertEqual(identity["sha1"], spec["sha1"])
                reconstruct.assert_called_once_with(region, {"synthetic.bin": chip})
                reconstruct.reset_mock()
                for bad in (chip[:-1], chip + b"x", b"x" * len(chip)):
                    path.write_bytes(bad)
                    with self.assertRaises(ValueError): audit.authenticate_chip(path)
                path.write_bytes(chip)
                for field in ("sha1", "crc32"):
                    with patch.dict(spec, {field: "0"}):
                        with self.assertRaises(ValueError): audit.authenticate_chip(path)
                reconstruct.assert_not_called()

    def test_cli_wrong_original_identity_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            chip, output = Path(directory) / "chip", Path(directory) / "report"
            chip.write_bytes(b"not-original")
            output.write_text("old", encoding="utf-8")
            with patch.object(audit, "analyze", side_effect=AssertionError("must authenticate first")):
                self.assertEqual(audit.main(["--chip", str(chip), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "old")

    def test_alias_and_hardlink_rejected_before_reading_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            chip, alias = Path(directory) / "chip", Path(directory) / "alias"
            chip.write_bytes(b"synthetic")
            os.link(chip, alias)
            with patch.object(audit, "authenticate_chip", side_effect=AssertionError("must guard first")):
                for output in (chip, alias):
                    self.assertEqual(audit.main(["--chip", str(chip), "--output", str(output)]), 2)
            self.assertEqual(chip.read_bytes(), b"synthetic")

    def test_symlink_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            chip, alias = Path(directory) / "chip", Path(directory) / "alias"
            chip.write_bytes(b"synthetic")
            try:
                alias.symlink_to(chip)
            except OSError:
                self.skipTest("Symlink creation unavailable on this host")
            with self.assertRaises(ValueError): audit.write_report(chip, alias, {})
            self.assertEqual(chip.read_bytes(), b"synthetic")

    def test_atomic_output_failure_preserves_report_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            chip, output = Path(directory) / "chip", Path(directory) / "report"
            chip.write_bytes(b"synthetic"); output.write_text("old", encoding="utf-8")
            with patch.object(audit.os, "replace", side_effect=OSError("denied")):
                with self.assertRaises(OSError): audit.write_report(chip, output, {"metadata": True})
            self.assertEqual(output.read_text(), "old")
            self.assertEqual(set(Path(directory).iterdir()), {chip, output})

    def test_successful_cli_emits_only_labeled_metadata(self):
        image = words(0, 0, 0x60, 8, 0x13fc, 0, 0x40, 1, 0xffff)
        with tempfile.TemporaryDirectory() as directory:
            chip, output = Path(directory) / "chip", Path(directory) / "report"
            chip.write_bytes(b"synthetic")
            with patch.object(audit, "authenticate_chip", return_value=(image, {"synthetic": True})):
                self.assertEqual(audit.main(["--chip", str(chip), "--output", str(output)]), 0)
            raw = output.read_bytes()
            report = json.loads(raw)
            self.assertEqual(report["entry"], audit.BASE + 8)
            self.assertEqual(len(report["store_candidates"]), 1)
            self.assertFalse(report["hardware_semantics_verified"])
            self.assertNotIn(b"\r", raw)
            for field in ("image", "rom_bytes", "opcode", "payload", "disassembly"):
                self.assertNotIn(f'"{field}":'.encode(), raw)


if __name__ == "__main__":
    unittest.main()
