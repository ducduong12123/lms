"""Subject-agnostic loop tests (no Frappe site needed):

python -m unittest lms.cognilearn.tests.test_adaptive
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta

from lms.cognilearn.core import adaptive, bkt
from lms.cognilearn.core.contracts import Condition
from lms.cognilearn.core.judge import FallbackJudge

T0 = datetime(2026, 10, 1, 9, 0)
# counting -> combinations -> classical probability -> conditional probability
EDGES = [("count", "comb"), ("comb", "prob"), ("prob", "cond")]
ORDER = ["count", "comb", "prob", "cond"]
Q = {
	"q1": ["count"],
	"q2": ["count"],
	"q3": ["comb"],
	"q4": ["comb"],
	"q5": ["prob", "comb"],
	"q6": ["prob"],
	"q7": ["cond"],
	"q8": ["cond", "prob"],
}
POOL = list(Q)


def attempts(member, results):
	return [adaptive.Attempt(member, q, ok, T0 + timedelta(minutes=i)) for i, (q, ok) in enumerate(results)]


class ShadowBKT(unittest.TestCase):
	def test_update_moves_toward_the_outcome(self):
		known = {}
		bkt.update(known, ["a"], True)
		self.assertGreater(known["a"], bkt.DEFAULT.p_init)
		before = known["a"]
		bkt.update(known, ["a"], False)
		self.assertLess(known["a"], before)

	def test_multi_kc_items_are_conjunctive(self):
		one = bkt.predict({}, ["a"])
		two = bkt.predict({}, ["a", "b"])
		self.assertAlmostEqual(two, one * one)
		self.assertIsNone(bkt.predict({}, []))


class Replay(unittest.TestCase):
	def test_predictions_are_logged_before_the_outcome(self):
		state = adaptive.replay_course(attempts("s1", [("q1", True), ("q1", True)]), Q)
		first, second = state.predictions
		self.assertEqual(first.elo_p, 0.5)  # nothing known yet
		self.assertGreater(second.elo_p, first.elo_p)
		self.assertGreater(second.bkt_p, first.bkt_p)

	def test_items_learn_from_every_learner(self):
		rows = attempts("s1", [("q3", False)]) + attempts("s2", [("q3", False)])
		state = adaptive.replay_course(rows, Q)
		self.assertGreater(state.item_ratings["q3"], 1000.0)  # failed by both -> harder

	def test_unmapped_questions_update_nothing(self):
		state = adaptive.replay_course(attempts("s1", [("q99", True)]), Q)
		self.assertEqual(state.unmapped, 1)
		self.assertEqual(state.learner("s1"), {})

	def test_teacher_correction_rescores_history(self):
		rows = attempts("s1", [("q3", False)])
		before = adaptive.replay_course(rows, Q).learner("s1")
		after = adaptive.replay_course(rows, {**Q, "q3": ["count"]}).learner("s1")
		self.assertIn("comb", before)
		self.assertNotIn("comb", after)
		self.assertIn("count", after)


class GuidedEvidence(unittest.TestCase):
	def test_hinted_answers_move_elo_less_and_bkt_not_at_all(self):
		free = adaptive.replay_course([adaptive.Attempt("a", "q1", True, T0)], Q)
		hinted = adaptive.replay_course([adaptive.Attempt("a", "q1", True, T0, "guided", 0.3)], Q)
		self.assertGreater(free.elo["a"]["count"].elo, hinted.elo["a"]["count"].elo)
		self.assertGreater(hinted.elo["a"]["count"].elo, 1000)
		self.assertEqual(hinted.bkt["a"], {})
		self.assertIn("count", free.bkt["a"])


class Diagnosis(unittest.TestCase):
	@staticmethod
	def mastery(**values):
		return {kc: {"mastery": value} for kc, value in values.items()}

	def test_weak_target_with_weak_prerequisite_practises_the_prerequisite(self):
		result = adaptive.diagnose(self.mastery(count=60, comb=48, prob=46), EDGES, ORDER)
		self.assertEqual(result.target_kc, "prob")
		self.assertEqual(result.focus_kc, "comb")
		self.assertEqual(result.reason, "gap")

	def test_gaps_are_most_foundational_first(self):
		result = adaptive.diagnose(self.mastery(count=49, comb=48, prob=47, cond=40), EDGES, ORDER)
		self.assertEqual(result.target_kc, "cond")
		self.assertEqual(result.prerequisite_gaps, ["count", "comb", "prob"])
		self.assertEqual(result.focus_kc, "count")

	def test_one_right_answer_is_not_weakness(self):
		# ~52% after a single correct answer: not weak, so the learner is not sent back to it.
		result = adaptive.diagnose(self.mastery(count=52.3, comb=52.3, prob=47.7), EDGES, ORDER)
		self.assertEqual((result.focus_kc, result.reason), ("prob", "weak"))

	def test_no_weakness_probes_the_most_advanced_unseen_kc(self):
		self.assertEqual(adaptive.diagnose(self.mastery(count=52), EDGES, ORDER).focus_kc, "cond")
		done = adaptive.diagnose(self.mastery(count=60, comb=60, prob=60, cond=60), EDGES, ORDER)
		self.assertEqual((done.focus_kc, done.reason), (None, "mastered"))

	def test_regress_moves_to_the_weakest_prerequisite(self):
		result = adaptive.diagnose(
			self.mastery(count=60, comb=52, prob=40), EDGES, ORDER, regress_from="prob"
		)
		self.assertEqual(result.focus_kc, "comb")

	def test_regress_probes_an_unseen_prerequisite_first(self):
		result = adaptive.diagnose(self.mastery(count=52, prob=40), EDGES, ORDER, regress_from="prob")
		self.assertEqual(result.focus_kc, "comb")

	def test_regress_without_a_shaky_prerequisite_sets_the_kc_aside(self):
		# "count" has no prerequisite: rather than drilling the same questions again, move on.
		weak_elsewhere = adaptive.diagnose(
			self.mastery(count=30, cond=45), EDGES, ORDER, regress_from="count"
		)
		self.assertEqual((weak_elsewhere.focus_kc, weak_elsewhere.target_kc), ("cond", "cond"))
		unseen_left = adaptive.diagnose(self.mastery(count=30), EDGES, ORDER, regress_from="count")
		self.assertEqual((unseen_left.focus_kc, unseen_left.reason), ("cond", "explore"))
		nothing_else = adaptive.diagnose(
			self.mastery(count=30, comb=60, prob=60, cond=60), EDGES, ORDER, regress_from="count"
		)
		self.assertEqual((nothing_else.focus_kc, nothing_else.reason), ("count", "weak"))

	def test_ancestors_handle_a_hand_made_cycle(self):
		self.assertEqual(set(adaptive.ancestors("a", [("a", "b"), ("b", "a")])), {"b"})


class Selection(unittest.TestCase):
	def select(self, condition, history, focus):
		return adaptive.select_items(
			condition,
			pool=POOL,
			q_matrix=Q,
			history=history,
			learner={},
			item_ratings={},
			focus_kc=focus,
			size=2,
		).questions

	def test_fixed_follows_course_order(self):
		self.assertEqual(self.select(Condition.FIXED, {"q1": True}, "cond"), ["q2", "q3"])

	def test_agentic_targets_the_focus_kc_unseen_first(self):
		self.assertEqual(self.select(Condition.AGENTIC, {"q3": True}, "comb"), ["q4", "q5"])

	def test_agentic_retries_wrong_answers_before_leaving_the_focus(self):
		self.assertEqual(
			self.select(Condition.AGENTIC, {"q3": False, "q4": True, "q5": True}, "comb"), ["q3", "q1"]
		)


class Replanning(unittest.TestCase):
	def test_thresholds(self):
		def action(results, condition=Condition.AGENTIC, done=1):
			return adaptive.replan(
				condition, set_results=results, sets_done=done, budget_sets=3, pool_left=5
			).action

		self.assertEqual(action([True, True, True, True]), "advance")
		self.assertEqual(action([True, False, False, False]), "regress")
		self.assertEqual(action([True, True, False, False]), "continue")
		self.assertEqual(action([False] * 4, Condition.FIXED), "continue")
		self.assertEqual(action([True] * 4, done=3), "schedule_recheck")

	def test_empty_pool_ends_practice(self):
		self.assertEqual(
			adaptive.replan(
				Condition.AGENTIC, set_results=[True], sets_done=1, budget_sets=3, pool_left=0
			).action,
			"schedule_recheck",
		)


class LeakGate(unittest.TestCase):
	class FakeJev:
		available = True
		source = "jev"

		def ask(self, state, questions):
			from lms.cognilearn.core.contracts import Judgment

			return {
				key: Judgment(
					question=key,
					value=0.9 if "5 bạn" in state["recheck"][int(key.split("_")[1])] else 0.1,
					source="jev",
				)
				for key in questions
			}

	def test_only_pairs_sharing_a_kc_are_judged(self):
		practice = [{"id": "q1", "text": "Có bao nhiêu cách xếp 5 bạn?"}, {"id": "q7", "text": "P(A|B)?"}]
		recheck = [{"id": "r1", "text": "Xếp 5 bạn vào 5 ghế"}, {"id": "r2", "text": "Xếp 6 bạn"}]
		checks = adaptive.find_leaks(
			self.FakeJev(), practice, recheck, {**Q, "r1": ["count"], "r2": ["count"]}
		)
		self.assertEqual(
			[(c["practice"], c["recheck"], c["leak"]) for c in checks],
			[("q1", "r1", True), ("q1", "r2", False)],
		)

	def test_without_jev_only_identical_text_leaks(self):
		practice = [{"id": "q1", "text": "Xếp  5 bạn"}]
		recheck = [{"id": "r1", "text": "xếp 5 bạn"}, {"id": "r2", "text": "Xếp 6 bạn"}]
		checks = adaptive.find_leaks(
			FallbackJudge(), practice, recheck, {**Q, "r1": ["count"], "r2": ["count"]}
		)
		self.assertEqual([c["leak"] for c in checks], [True, False])


class ResearchMetrics(unittest.TestCase):
	def test_kappa_and_auc(self):
		from lms.cognilearn.research.tatsuoka_benchmark import auc, kappa

		self.assertEqual(kappa([(1, 1), (0, 0), (1, 1), (0, 0)]), 1.0)
		self.assertEqual(kappa([(1, 0), (0, 1), (1, 0), (0, 1)]), -1.0)
		self.assertEqual(auc([(0.9, 1), (0.1, 0)]), 1.0)
		self.assertEqual(auc([(0.5, 1), (0.5, 0)]), 0.5)

	def test_benchmark_data_is_complete(self):
		from lms.cognilearn.research import tatsuoka_benchmark as t

		self.assertEqual(len(t.ITEMS), 20)
		self.assertEqual(len(t.EXPERT), 20)
		self.assertTrue(all(len(row) == 8 and set(row) <= {"0", "1"} for row in t.EXPERT))
		self.assertEqual([len(t.ATTRIBUTES[lang]) for lang in ("en", "vi")], [8, 8])

	def test_logged_and_replayed_predictions_agree(self):
		from lms.cognilearn.research.model_comparison import compare

		rows = [
			{
				"member": "m",
				"item": q,
				"correct": str(int(ok)),
				"source": "practice",
				"mode": "independent",
				"concepts": json.dumps(Q[q]),
				"at": (T0 + timedelta(minutes=i)).isoformat(),
				"elo_p": "",
				"bkt_p": "",
			}
			for i, (q, ok) in enumerate([("q1", True), ("q2", False), ("q3", True), ("q1", True)])
		]
		state = adaptive.replay_course(
			[
				adaptive.Attempt("m", r["item"], r["correct"] == "1", datetime.fromisoformat(r["at"]))
				for r in rows
			],
			Q,
		)
		for row, prediction in zip(rows, state.predictions, strict=True):
			row["elo_p"], row["bkt_p"] = str(prediction.elo_p), str(prediction.bkt_p)
		result = compare(rows)
		self.assertEqual(result["logged"], result["replayed"])


if __name__ == "__main__":
	unittest.main()
