"""Tests for the human-reviewed, versioned HOTD1 project-wide progress tool.

All progress data is metadata. No Sega program, device firmware or ROM bytes.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from arcaderecomp.progress import (
    DEFAULT_PATH, ProgressError, change, load, main, save, text_status, validate
)


class ProgressTrackerTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load(DEFAULT_PATH)

    def test_imported_baseline_is_complete_estimate_not_a_hardware_claim(self):
        data = self.baseline
        index = validate(data)
        self.assertEqual(data["overall"]["percent"], 10)
        self.assertEqual({g["id"]: g["complete"] for g in data["gates"]},
                         {"A": False, "B": False, "C": False})
        self.assertEqual({a["id"]: a["percent"] for a in data["areas"]}, {
            "rom": 95, "cpu": 55, "model2c": 20, "gun": 5,
            "graphics": 0, "audio": 0, "gameplay": 0, "tools": 85,
        })
        self.assertEqual(len(index), 1 + 8 + 85 + 6)
        self.assertEqual(index["model2c.tx_callbacks"]["percent"], 100)
        self.assertEqual(index["model2c.authentic_rx"]["percent"], 5)
        self.assertEqual(index["gameplay.boot"]["percent"], 0)
        self.assertEqual(index["graphics.aot"]["percent"], 0)
        self.assertEqual(index["audio.scsp"]["percent"], 0)
        self.assertTrue(all(x["excluded_from_hotd1_overall"]
                            for x in data["future_targets"]))

    def test_review_preserves_percentage_and_adds_auditable_entry(self):
        changed = change(self.baseline, "model2c", percent=None,
                         note="The serial byte capture was inspected; still no independently verified cabinet RX trace.",
                         evidence=["docs/SEGA_IO3155649.md"],
                         today="2026-10-11")
        self.assertEqual(changed["areas"][2]["percent"], 20)
        self.assertEqual(changed["history"][-1]["kind"], "review")
        self.assertEqual(changed["history"][-1]["percent_before"], 20)
        self.assertEqual(changed["history"][-1]["percent_after"], 20)
        self.assertEqual(self.baseline["history"][0]["kind"], "baseline")
        validate(changed)

    def test_justified_increments_and_regressions_are_accepted(self):
        raised = change(self.baseline, "cpu.floating", percent=45,
                        note="A specific synthetic instruction case passed native parity but hardware remains unverified.",
                        evidence=["tests/test_i960_subr_native.py"], today="2026-10-11")
        self.assertEqual(validate(raised)["cpu.floating"]["percent"], 45)
        down = change(raised, "cpu.floating", percent=40,
                      note="Hardware comparison invalidated the previously counted coverage and requires rework.",
                      evidence=["docs/MODEL2C_HARDWARE.md"],
                      today="2026-10-12")
        self.assertEqual(validate(down)["cpu.floating"]["percent"], 40)
        self.assertEqual(
            [(x["percent_before"], x["percent_after"])
             for x in down["history"][-2:]],
            [(40, 45), (45, 40)])
        self.assertEqual(down["overall"]["percent"], 10)
        self.assertEqual(self.baseline["areas"][1]["tasks"][9]["percent"], 40)

    def test_percent_cannot_be_inflated_automatically(self):
        for pct in (True, -1, 101, 101.0):
            with self.subTest(pct=pct):
                with self.assertRaises(ProgressError):
                    change(self.baseline, "cpu.floating", percent=pct,
                           note="A test failure or suspect automated percentage.",
                           evidence=["tests/test_i960_subr_native.py"])
        with self.assertRaisesRegex(ProgressError, "use the review"):
            change(self.baseline, "cpu.floating", percent=40,
                   note="No measured change, do not fabricate progress.",
                   evidence=["tests/test_i960_subr_native.py"])
        with self.assertRaisesRegex(ProgressError, "evidence"):
            change(self.baseline, "cpu.floating", percent=45,
                   note="Do not take unsubstantiated claims as evidence.",
                   evidence=[])
        with self.assertRaisesRegex(ProgressError, "note"):
            change(self.baseline, "cpu.floating", percent=45,
                   note="done", evidence=["tests/test_i960_subr_native.py"])
        with self.assertRaisesRegex(ProgressError, "unknown progress"):
            change(self.baseline, "invented.section", percent=45,
                   note="This ID must be in the project-wide schema.",
                   evidence=["docs/ROADMAP.md"])

    def test_100_percent_game_blocked_without_completion_gates(self):
        with self.assertRaisesRegex(ProgressError, "verified Gate C"):
            change(self.baseline, "hotd1", percent=100,
                   note="A single synthetic or native instruction test is not end-to-end gameplay.",
                   evidence=["docs/MODEL2C_DEFINITION_OF_DONE.md"])
        for target in ("A", "B", "C"):
            broken = deepcopy(self.baseline)
            for gate in broken["gates"]:
                if gate["id"] == target:
                    gate["complete"] = True
                    gate["evidence"] = ["docs/MODEL2C_DEFINITION_OF_DONE.md"]
            with self.subTest(gate=target):
                with self.assertRaises(ProgressError):
                    validate(broken)

    def test_reject_duplicate_tasks_corrupt_history_and_false_target_weight(self):
        duplicate = deepcopy(self.baseline)
        duplicate["areas"][1]["tasks"].append(
            deepcopy(duplicate["areas"][1]["tasks"][0]))
        with self.assertRaisesRegex(ProgressError, "unique"):
            validate(duplicate)
        wrong = deepcopy(self.baseline)
        wrong["overall"]["percent"] = 95
        with self.assertRaisesRegex(ProgressError, "history"):
            validate(wrong)
        wrong = deepcopy(self.baseline)
        wrong["future_targets"][0]["excluded_from_hotd1_overall"] = False
        with self.assertRaisesRegex(ProgressError, "excluded"):
            validate(wrong)
        wrong = deepcopy(self.baseline)
        wrong["history"][0]["kind"] = "review"
        with self.assertRaises(ProgressError):
            validate(wrong)

    def test_history_replay_rejects_inconsistent_edits(self):
        doc = change(self.baseline, "cpu", percent=60,
                     note="Recorded a bounded architecture improvement with linked tests.",
                     evidence=["tests/test_i960_subr_native.py"],
                     today="2026-10-11")
        doc = change(doc, "cpu", percent=65,
                     note="Another separately evidenced improvement in CPU functional coverage.",
                     evidence=["docs/I960_FRAMES.md"],
                     today="2026-10-12")
        doc["history"][-1]["percent_before"] = 55
        with self.assertRaisesRegex(ProgressError, "broken percentage"):
            validate(doc)

    def test_save_and_cli_roundtrip_without_touching_source(self):
        # Derive the test update from the current tracker baseline rather
        # than assuming a software-framework estimate never changes.
        starting_percent = next(
            t["percent"]
            for area in self.baseline["areas"]
            for t in area["tasks"]
            if t["id"] == "model2c.rx_framework"
        )
        target_percent = starting_percent + 5
        self.assertLessEqual(target_percent, 100)
        with tempfile.TemporaryDirectory(prefix="hotdo-progress-") as d:
            target = Path(d) / "progress.json"
            save(target, self.baseline)
            self.assertEqual(load(target), self.baseline)
            self.assertEqual(main(["--file", str(target), "validate"]), 0)
            self.assertEqual(main(["--file", str(target), "status",
                                   "--tasks"]), 0)
            self.assertEqual(main(["--file", str(target), "status",
                                   "--json"]), 0)
            self.assertEqual(main(["--file", str(target), "update",
                                   "--id", "model2c.rx_framework", "--percent", str(target_percent),
                                   "--note", "Validated new externally supplied serial RX framing against the synthetic regression.",
                                   "--evidence", "tests/test_sega_serial_events.py",
                                   "--dry-run"]), 0)
            self.assertEqual(load(target), self.baseline)
            self.assertEqual(main(["--file", str(target), "review",
                                   "--id", "model2c", "--note",
                                   "The real serial status timing is still unverified despite continued research.",
                                   "--evidence", "docs/SEGA_IO3155649.md"]), 0)
            revised = load(target)
            self.assertEqual(revised["history"][-1]["kind"], "review")
            self.assertEqual(revised["areas"][2]["percent"], 20)
            self.assertEqual(main(["--file", str(target), "update",
                                   "--id", "model2c.rx_framework",
                                   "--percent", str(target_percent),
                                   "--note", "The explicit synthetic model was expanded but no cabinet proof was obtained.",
                                   "--evidence", "tests/test_sega_serial_events.py"]), 0)
            final = load(target)
            self.assertEqual(validate(final)["model2c.rx_framework"]["percent"], target_percent)
            self.assertEqual(final["history"][-1]["percent_before"], starting_percent)
            self.assertEqual(final["history"][-1]["percent_after"], target_percent)
            self.assertEqual(json.loads(target.read_text()), final)
            self.assertEqual([p.name for p in Path(d).iterdir()], ["progress.json"])

    def test_text_status_disclaims_not_measured_and_shows_next_steps(self):
        output = text_status(self.baseline, show_tasks=True)
        self.assertIn("~10%", output)
        self.assertIn("NOT a measured coverage percentage", output)
        self.assertIn("cpu.rounding", output)
        self.assertIn("model2c.authentic_rx", output)
        self.assertIn("NEXT:", output)
        self.assertIn("excluded from original HOTD1 overall", output)


if __name__ == "__main__":
    unittest.main()
