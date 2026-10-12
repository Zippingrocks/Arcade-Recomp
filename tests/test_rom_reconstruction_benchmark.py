"""Check benchmark parity/reporting; speed is deliberately not a CI assertion."""
import unittest

from tools.benchmark_rom_reconstruction import benchmark, cases


class ReconstructionBenchmarkTests(unittest.TestCase):
    def test_tiny_synthetic_benchmark_checks_every_case(self):
        report = benchmark(rounds=1, chip_kib=1)
        self.assertEqual(report["rounds"], 1)
        self.assertEqual(len(report["cases"]), 4)
        self.assertIn("not gameplay FPS", report["scope"])
        for row in report["cases"]:
            self.assertGreater(row["baseline_median_ms"], 0)
            self.assertGreater(row["current_median_ms"], 0)
            self.assertGreater(row["speedup"], 0)
            self.assertEqual(len(row["sha256"]), 64)
            self.assertIn(row["region_bytes"], (1024, 2048))

    def test_benchmark_rejects_unbounded_sizes_and_trials(self):
        for value in (0, -1, 16385):
            with self.assertRaises(ValueError):
                list(cases(value))
        for value in (0, -1, 101):
            with self.assertRaises(ValueError):
                benchmark(rounds=value, chip_kib=1)


if __name__ == "__main__":
    unittest.main()
