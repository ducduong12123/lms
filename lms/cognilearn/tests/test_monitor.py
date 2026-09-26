"""Dashboard summaries (no Frappe site needed):

python -m unittest lms.cognilearn.tests.test_monitor
"""

from __future__ import annotations

import unittest

from lms.cognilearn.core import adaptive, monitor


class MasteryBand(unittest.TestCase):
	def test_no_evidence_is_its_own_band(self):
		self.assertEqual(monitor.mastery_band(None), monitor.NONE)
		self.assertEqual(monitor.mastery_band({"mastery": 80.0, "attempts": 0}), monitor.NONE)

	def test_bands_follow_the_policy_thresholds(self):
		def band(mastery):
			return monitor.mastery_band({"mastery": mastery, "attempts": 3})

		self.assertEqual(band(adaptive.WEAK_BELOW - 0.1), monitor.SHAKY)
		self.assertEqual(band(adaptive.WEAK_BELOW), monitor.GROWING)
		self.assertEqual(band(adaptive.SOLID_AT), monitor.SOLID)


class Prediction(unittest.TestCase):
	def test_only_rows_both_models_scored_count(self):
		rows = [
			{"correct": 1, "elo_p": 0.9, "bkt_p": 0.6},
			{"correct": 0, "elo_p": 0.2, "bkt_p": 0.7},
			{"correct": 1, "elo_p": 0.5, "bkt_p": None},
		]
		result = monitor.compare_logged(rows)
		self.assertEqual(result["elo"]["n"], 2)
		self.assertEqual(result["elo"]["auc"], 1.0)
		self.assertEqual(result["bkt"]["auc"], 0.0)

	def test_auc_needs_both_outcomes(self):
		self.assertIsNone(monitor.auc([(0.4, 1), (0.6, 1)]))


class ArmSummary(unittest.TestCase):
	def test_gain_uses_only_learners_with_both_scores(self):
		def learner(baseline, recheck):
			return {
				"baseline": baseline,
				"recheck": recheck,
				"practice_answers": 6,
				"practice_correct": 3,
				"items": 6,
				"hinted_items": 2,
				"lessons_done": 1,
			}

		summary = monitor.arm_summary([learner(40.0, 70.0), learner(60.0, None)])
		self.assertEqual(summary["n"], 2)
		self.assertEqual(summary["baseline"], 50.0)
		self.assertEqual(summary["gain"], 30.0)
		self.assertEqual(summary["with_recheck"], 1)
		self.assertEqual(summary["practice_accuracy"], 50.0)
		self.assertAlmostEqual(summary["hint_rate"], 33.3)

	def test_empty_arm(self):
		summary = monitor.arm_summary([])
		self.assertEqual(summary["n"], 0)
		self.assertIsNone(summary["gain"])
		self.assertIsNone(summary["practice_accuracy"])


if __name__ == "__main__":
	unittest.main()
