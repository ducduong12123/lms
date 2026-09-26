"""Inner-loop tests (no Frappe site needed):

python -m unittest lms.cognilearn.tests.test_inner_loop
"""

from __future__ import annotations

import json
import unittest

from lms.cognilearn.core import hints, inner_loop
from lms.cognilearn.core.inner_loop import CONCEPT, SOLUTION, STEP, ItemState
from lms.cognilearn.core.judge import FallbackJudge
from lms.cognilearn.tests.test_core import FakeJev

AT = "2026-10-01T09:00:00"


def at(seconds: float) -> str:
	return f"2026-10-01T09:{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


class Ladder(unittest.TestCase):
	def test_levels_come_in_order_and_skip_missing_content(self):
		self.assertEqual(inner_loop.next_hint({CONCEPT, STEP, SOLUTION}, []), CONCEPT)
		self.assertEqual(inner_loop.next_hint({CONCEPT, STEP, SOLUTION}, [CONCEPT]), STEP)
		self.assertEqual(inner_loop.next_hint({CONCEPT, SOLUTION}, [CONCEPT]), SOLUTION)
		self.assertIsNone(inner_loop.next_hint({CONCEPT, SOLUTION}, [CONCEPT, SOLUTION]))

	def test_one_retry_after_a_wrong_answer(self):
		item = ItemState()
		self.assertTrue(inner_loop.can_answer(item))
		self.assertFalse(inner_loop.retry_allowed(item))
		item.tries.append({"answer": "a", "correct": False, "at": AT})
		self.assertTrue(inner_loop.retry_allowed(item))
		item.tries.append({"answer": "b", "correct": False, "at": at(20)})
		self.assertTrue(item.finished)
		self.assertFalse(inner_loop.can_answer(item))

	def test_right_first_time_or_solution_ends_the_question(self):
		solved = ItemState(tries=[{"answer": "a", "correct": True, "at": AT}])
		self.assertTrue(solved.finished)
		gave_up = ItemState(hints=[{"level": SOLUTION, "at": AT}])
		self.assertTrue(gave_up.finished)
		self.assertIsNone(gave_up.first_correct)

	def test_state_round_trips_through_json(self):
		item = ItemState(
			hints=[{"level": CONCEPT, "at": AT}], tries=[{"answer": "x", "correct": False, "at": AT}]
		)
		self.assertEqual(ItemState.from_dict(json.loads(json.dumps(item.to_dict()))), item)


class Measurement(unittest.TestCase):
	def test_unaided_first_answer_is_full_evidence(self):
		evidence = inner_loop.evidence_for_first_answer(ItemState(), True)
		self.assertEqual((evidence.mode, evidence.weight, evidence.hints_used), ("independent", 1.0, 0))

	def test_hints_before_the_first_answer_make_it_guided(self):
		concept = ItemState(hints=[{"level": CONCEPT, "at": AT}])
		step = ItemState(hints=[{"level": CONCEPT, "at": AT}, {"level": STEP, "at": AT}])
		self.assertEqual(inner_loop.evidence_for_first_answer(concept, True).weight, 0.45)
		guided = inner_loop.evidence_for_first_answer(step, True)
		self.assertEqual(
			(guided.mode, guided.weight, guided.max_hint, guided.hints_used), ("guided", 0.3, STEP, 2)
		)

	def test_solution_before_answering_counts_as_not_knowing(self):
		evidence = inner_loop.evidence_for_solution_first(ItemState(hints=[{"level": CONCEPT, "at": AT}]))
		self.assertEqual((evidence.correct, evidence.mode, evidence.max_hint), (False, "guided", SOLUTION))

	def test_help_seeking_flags(self):
		rushed = ItemState(hints=[{"level": SOLUTION, "at": AT}])
		self.assertEqual(inner_loop.gaming_flags(rushed), ["solution_without_trying"])
		guessing = ItemState(
			tries=[
				{"answer": "a", "correct": False, "at": at(10)},
				{"answer": "b", "correct": True, "at": at(11)},
			]
		)
		self.assertEqual(inner_loop.gaming_flags(guessing), ["quick_retry"])
		ladder_rush = ItemState(hints=[{"level": STEP, "at": at(10)}, {"level": SOLUTION, "at": at(12)}])
		self.assertIn("quick_solution", inner_loop.gaming_flags(ladder_rush))
		thoughtful = ItemState(
			hints=[{"level": CONCEPT, "at": at(0)}],
			tries=[
				{"answer": "a", "correct": False, "at": at(40)},
				{"answer": "b", "correct": True, "at": at(90)},
			],
		)
		self.assertEqual(inner_loop.gaming_flags(thoughtful), [])


ITEM = {
	"question": "Điểm thi có trung bình 6 và độ lệch chuẩn 1,5. Điểm z của sinh viên được 9 điểm là bao nhiêu?",
	"options": ["2", "3", "1,5", "0,5"],
	"correct": ["2"],
	"solution": "(9 − 6) / 1,5 = 2.",
	"concepts": ["Tính và diễn giải điểm z"],
}


class ScriptedLLM:
	def __init__(self, *replies):
		self.replies = list(replies)
		self.prompts = []

	def chat(self, system, user):
		self.prompts.append(user)
		return self.replies.pop(0)


class StepHints(unittest.TestCase):
	@staticmethod
	def jev(leak, faithful=0.95, on_concept=0.95):
		table = {"leaks": leak, "faithful": faithful, "on_concept": on_concept}
		return FakeJev(lambda state, key: table[key](state) if callable(table[key]) else table[key])

	def test_a_hint_that_passes_every_check_is_accepted(self):
		llm = ScriptedLLM('{"hint": "Bạn hãy dùng công thức z = (x − trung bình) / độ lệch chuẩn."}')
		result = hints.generate_step_hint(llm, self.jev(0.05), ITEM)
		self.assertEqual(result.status, "Accepted")
		self.assertEqual(result.judge_source, "jev")
		self.assertEqual(len(result.attempts), 1)

	def test_a_leaking_hint_is_rewritten_once_with_the_reason(self):
		leaky = '{"hint": "Tính (9 − 6) / 1,5 = 2 là xong."}'
		clean = '{"hint": "Bạn hãy so sánh điểm 9 với trung bình theo đơn vị độ lệch chuẩn."}'
		llm = ScriptedLLM(leaky, clean)
		judge = self.jev(lambda state: 0.9 if "= 2" in state["hint"] else 0.1)
		result = hints.generate_step_hint(llm, judge, ITEM)
		self.assertEqual(result.status, "Accepted")
		self.assertIn("lộ đáp án", llm.prompts[1])
		self.assertEqual(len(result.attempts), 2)

	def test_two_failures_leave_no_step_hint(self):
		llm = ScriptedLLM('{"hint": "Đáp án là 2."}', '{"hint": "Chọn 2."}')
		result = hints.generate_step_hint(llm, self.jev(0.95), ITEM)
		self.assertEqual(result.status, "Rejected")
		self.assertEqual(result.p_leak, 0.95)

	def test_a_wrong_hint_is_rejected_even_if_it_does_not_leak(self):
		llm = ScriptedLLM('{"hint": "Nhân 9 với 1,5."}', '{"hint": "Nhân 9 với 1,5."}')
		result = hints.generate_step_hint(llm, self.jev(0.05, faithful=0.1), ITEM)
		self.assertEqual(result.status, "Rejected")

	def test_without_jev_no_hint_is_shown(self):
		llm = ScriptedLLM('{"hint": "Dùng công thức điểm z."}', '{"hint": "x"}')
		result = hints.generate_step_hint(llm, FallbackJudge(), ITEM)
		self.assertEqual((result.status, len(result.attempts)), ("Rejected", 1))

	def test_a_broken_llm_reply_is_a_rejection_not_a_crash(self):
		result = hints.generate_step_hint(ScriptedLLM('{"hint": ', ""), self.jev(0.05), ITEM)
		self.assertEqual(result.status, "Rejected")
		self.assertIsNone(result.text)

	def test_plain_text_and_json_replies_both_work(self):
		plain = hints.generate_step_hint(ScriptedLLM("Dùng công thức điểm z."), self.jev(0.05), ITEM)
		fenced = hints.generate_step_hint(
			ScriptedLLM('```json\n{"hint": "Dùng công thức điểm z."}\n```'), self.jev(0.05), ITEM
		)
		self.assertEqual(plain.text, "Dùng công thức điểm z.")
		self.assertEqual(fenced.text, "Dùng công thức điểm z.")


if __name__ == "__main__":
	unittest.main()
