"""Enforcement tests: code edits require append-only progress review."""
from copy import deepcopy
import unittest

from arcaderecomp.progress import DEFAULT_PATH, ProgressError, change, load
from arcaderecomp.progress_guard import TRACKER, check_changes


class ProgressGuardTests(unittest.TestCase):
    def setUp(self):
        self.previous = load(DEFAULT_PATH)
        self.revised = change(
            self.previous, "cpu", percent=None,
            note="The native regression was inspected; no new hardware fidelity was verified.",
            evidence=["tests/test_progress_guard.py"],
            today="2026-10-11")

    def test_implementation_rejected_without_tracker_change(self):
        for changed in (
            {"runtime/model2c_bus.hpp"},
            {"arcaderecomp/i960_cpp.py", "tests/test_i960_subr_native.py"},
            {".github/workflows/tests.yml"},
            {"tools/hotd1_strict_boot_probe.cpp"},
            {"targets/hotd1/original.json"},
        ):
            with self.subTest(files=changed):
                with self.assertRaisesRegex(ProgressError, "was not updated"):
                    check_changes(changed, self.previous, self.revised)

    def test_implementation_requires_new_history_not_just_modified_json(self):
        changed = {"runtime/model2c_bus.hpp", TRACKER}
        with self.assertRaisesRegex(ProgressError, "append"):
            check_changes(changed, self.previous, self.previous)
        edited = deepcopy(self.revised)
        edited["history"][0]["note"] += " edited after the fact"
        with self.assertRaisesRegex(ProgressError, "append"):
            check_changes(changed, self.previous, edited)

    def test_review_with_no_inflation_satisfies_guard(self):
        self.assertTrue(check_changes(
            {"runtime/model2c_bus.hpp", TRACKER},
            self.previous, self.revised))
        self.assertEqual(self.revised["overall"]["percent"], 10)
        self.assertEqual(self.revised["areas"][1]["percent"], 55)
        self.assertEqual(self.revised["history"][-1]["kind"], "review")

    def test_scoped_estimate_change_satisfies_guard(self):
        changed = change(
            self.previous, "cpu.floating", percent=45,
            note="A supported native instruction was checked against independent reference data.",
            evidence=["tests/test_i960_subr_native.py"],
            today="2026-10-11")
        self.assertTrue(check_changes({"arcaderecomp/i960_cpp.py", TRACKER},
                                      self.previous, changed))

    def test_docs_only_and_progress_only_changes_do_not_need_new_history(self):
        self.assertFalse(check_changes({"docs/ROADMAP.md"}, self.previous,
                                       self.previous))
        self.assertFalse(check_changes({TRACKER}, self.previous,
                                       self.previous))
        self.assertFalse(check_changes(set(), self.previous, self.previous))

    def test_initial_baseline_only_for_tracker_creation(self):
        self.assertTrue(check_changes({"runtime/model2c_bus.hpp", TRACKER},
                                      None, self.previous))


if __name__ == "__main__":
    unittest.main()
