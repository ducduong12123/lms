"""Core tests. Plain unittest, no Frappe site needed:

    python -m unittest lms.cognilearn.tests.test_core
"""

from __future__ import annotations

import ast
import pathlib
import unittest
from datetime import datetime, timedelta

from lms.cognilearn.core import content_sll, elo, evaluator, policy
from lms.cognilearn.core.contracts import Condition
from lms.cognilearn.core.judge import FallbackJudge, JevJudge, ask_safely, noul, route
from lms.cognilearn.core.knowledge_map import build_knowledge_map, propose_components, similarity, slug

CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / "core"
ITEMS = content_sll.items()
BY_CODE = {item["code"]: item for item in ITEMS}


class CoreIsPlatformIndependent(unittest.TestCase):
	def test_core_never_imports_frappe(self):
		for path in CORE_DIR.glob("*.py"):
			tree = ast.parse(path.read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				names = []
				if isinstance(node, ast.Import):
					names = [alias.name for alias in node.names]
				elif isinstance(node, ast.ImportFrom):
					names = [node.module or ""]
				for name in names:
					self.assertFalse(name == "frappe" or name.startswith("frappe."), f"{path.name} imports {name}")


class ContentAndEvaluator(unittest.TestCase):
	def test_manifest_is_valid(self):
		self.assertEqual(evaluator.validate_items(ITEMS, content_sll.TARGET_CONCEPT), [])
		self.assertEqual(len(ITEMS), 13)

	def test_prerequisite_graph_is_acyclic_and_closed(self):
		for source, target in content_sll.PREREQUISITES:
			self.assertIn(source, content_sll.KNOWLEDGE_COMPONENTS)
			self.assertIn(target, content_sll.KNOWLEDGE_COMPONENTS)
		for item in ITEMS:
			for tag in item["concepts"] + item["prerequisites"]:
				self.assertIn(tag, content_sll.KNOWLEDGE_COMPONENTS, item["code"])

	def test_mcq_letter_index_and_misconception(self):
		item = BY_CODE["SLL-PILOT-B-01"]
		self.assertTrue(evaluator.evaluate(item, "B").is_correct)
		self.assertTrue(evaluator.evaluate(item, "1").is_correct)
		wrong = evaluator.evaluate(item, "A")
		self.assertFalse(wrong.is_correct)
		self.assertEqual(wrong.misconception_code, "lost_successor")

	def test_tracing_and_pointer_order(self):
		self.assertTrue(evaluator.evaluate(BY_CODE["SLL-PILOT-G-01"], "3 -> 4 -> 5 -> 7").is_correct)
		ordered = BY_CODE["SLL-PILOT-G-02"]
		self.assertTrue(evaluator.evaluate(ordered, ["B", "A"]).is_correct)
		self.assertFalse(evaluator.evaluate(ordered, ["A", "B"]).is_correct)
		self.assertFalse(evaluator.evaluate(ordered, "node_k->next = new_node").is_correct)
		self.assertTrue(evaluator.evaluate(ordered, "new_node->next = node_k->next;\nnode_k->next = new_node;").is_correct)

	def test_hint_ladder_stays_on_last_level(self):
		item = BY_CODE["SLL-PILOT-G-01"]
		self.assertNotEqual(evaluator.hint_for_item(item, 0), evaluator.hint_for_item(item, 1))
		self.assertEqual(evaluator.hint_for_item(item, 1), evaluator.hint_for_item(item, 9))
		self.assertNotIn("3 -> 4 -> 5 -> 7", evaluator.hint_for_item(item, 9))

	def test_public_item_hides_answers(self):
		public = evaluator.public_item(BY_CODE["SLL-PILOT-B-02"])
		for secret in ("correct_answer", "accepted_answers", "misconception_by_answer", "hint_ladder"):
			self.assertNotIn(secret, public)


class EloModel(unittest.TestCase):
	def test_worked_example_from_explainer(self):
		# Learner 1000 vs hard item 1100: E = 0.36; independent correct +20.5, guided +7.2, wrong -11.5.
		self.assertAlmostEqual(elo.expected(1000, 1100), 0.36, places=2)
		for mode, correct, delta in (("independent", True, 20.5), ("guided", True, 7.2), ("independent", False, -11.5)):
			states: dict = {}
			elo.apply_attempt(states, {}, item_code="x", difficulty="hard", concepts=["c"], correct=correct, mode=mode, at=datetime(2026, 9, 26))
			self.assertAlmostEqual(states["c"].elo - 1000, delta, places=1)

	def test_guided_weight_is_capped(self):
		self.assertEqual(elo.evidence_weight("guided"), 0.35)
		self.assertEqual(elo.evidence_weight("guided", 1.0), 0.45)
		self.assertEqual(elo.evidence_weight("independent"), 1.0)

	def test_q_mask_splits_weight(self):
		states: dict = {}
		elo.apply_attempt(states, {}, item_code="x", difficulty="medium", concepts=["a", "b"], correct=True, mode="independent", at=datetime(2026, 9, 26))
		self.assertAlmostEqual(states["a"].weight_sum, 1 / 2**0.5, places=4)

	def test_decay_moves_toward_prior(self):
		states: dict = {}
		start = datetime(2026, 9, 1)
		for _ in range(6):
			elo.apply_attempt(states, {}, item_code="x", difficulty="hard", concepts=["c"], correct=True, mode="independent", at=start)
		fresh = elo.decayed_mastery(states["c"], start)
		later = elo.decayed_mastery(states["c"], start + timedelta(days=14))
		self.assertGreater(fresh, later)
		self.assertAlmostEqual(later - 50.0, (fresh - 50.0) / 2, delta=0.2)

	def test_replay_is_order_independent_of_input_order(self):
		rows = [
			{"item_code": "a", "difficulty": "easy", "concepts": ["c"], "correct": True, "mode": "independent", "at": datetime(2026, 9, 1)},
			{"item_code": "b", "difficulty": "hard", "concepts": ["c"], "correct": False, "mode": "guided", "at": datetime(2026, 9, 2)},
		]
		first, _ = elo.replay(rows)
		second, _ = elo.replay(list(reversed(rows)))
		self.assertEqual(first["c"].elo, second["c"].elo)


class Policy(unittest.TestCase):
	def test_blocks_of_four_are_balanced(self):
		for block in range(5):
			assigned = [policy.assign_condition(block * 4 + slot) for slot in range(4)]
			self.assertEqual(assigned.count(Condition.AGENTIC), 2)

	def test_agentic_orders_by_observed_misconception(self):
		diagnosis = policy.build_diagnosis(
			[{"item_code": "SLL-PILOT-B-03", "correct": False, "misconception_code": "wrong_k_boundary", "prerequisites": ["traversal_counting"]}]
		)
		agentic = policy.build_plan(Condition.AGENTIC, diagnosis, ITEMS)
		fixed = policy.build_plan(Condition.FIXED, diagnosis, ITEMS)
		self.assertEqual(agentic.guided_item_codes[0], "SLL-PILOT-G-01")
		self.assertEqual(fixed.guided_item_codes, content_sll.item_codes_for_stage("guided_practice"))
		self.assertEqual(sorted(agentic.guided_item_codes), sorted(fixed.guided_item_codes))

	def test_replan_thresholds(self):
		self.assertEqual(policy.build_replan(Condition.AGENTIC, [], 1.0).next_action, "schedule_recheck")
		self.assertEqual(policy.build_replan(Condition.AGENTIC, [], 0.0).next_action, "regress")
		self.assertEqual(policy.build_replan(Condition.AGENTIC, [], 0.5).next_action, "continue")
		guided_wrong = [{"item_code": "g", "mode": "guided", "correct": False}]
		self.assertEqual(policy.build_replan(Condition.AGENTIC, guided_wrong).next_action, "continue_guided")
		self.assertEqual(policy.build_replan(Condition.FIXED, guided_wrong, 0.0).next_action, "schedule_recheck")


class FakeLLM:
	def __init__(self, reply: str):
		self.reply = reply

	def chat(self, system: str, user: str) -> str:
		return self.reply


class FakeJev(JevJudge):
	"""Answers from a table keyed by the instruction text and state."""

	def __init__(self, decide):
		super().__init__("test-key", post=self._post)
		self.decide = decide
		self.requests = 0

	def _post(self, url, payload, headers, timeout):
		self.requests += 1
		answers = {key: {"type": "noul", "noul": self.decide(payload["state"], key)} for key in payload["questions"]}
		return {"answers": answers}


COURSE = {
	"name": "dslk",
	"title": "Danh sách liên kết",
	"lessons": [
		{"id": "L1", "title": "Node", "text": "...", "questions": [{"id": "Q1", "text": "Node gồm những trường nào?"}]},
		{"id": "L2", "title": "Chèn", "text": "...", "questions": [{"id": "Q2", "text": "Chèn sau k"}]},
	],
}
CATALOGUE = [
	{"key": "node_structure", "label": "Cấu trúc node", "description": "", "prerequisites": [], "lessons": ["L1"], "questions": ["Q1"]},
	{"key": "insert_after_k", "label": "Chèn sau k", "description": "", "prerequisites": ["node_structure"], "lessons": ["L2"], "questions": ["Q2"]},
	{"key": "node_structure_basics", "label": "Cấu trúc node cơ bản", "description": "", "prerequisites": [], "lessons": ["L2"], "questions": []},
]


class KnowledgeMapping(unittest.TestCase):
	def test_slug_and_similarity(self):
		self.assertEqual(slug("Chèn sau vị trí k"), "chen_sau_vi_tri_k")
		self.assertGreater(similarity({"key": "node_structure", "label": "x"}, {"key": "node_structure_basics", "label": "x"}), 0.34)

	def test_route(self):
		self.assertEqual(route(0.9, 0.8, 0.2), "accepted")
		self.assertEqual(route(0.1, 0.8, 0.2), "rejected")
		self.assertEqual(route(0.5, 0.8, 0.2), "review")
		self.assertEqual(route(None, 0.8, 0.2), "review")

	def test_fallback_sends_llm_proposals_to_review(self):
		result = build_knowledge_map(COURSE, llm=None, judge=FallbackJudge(), catalogue=CATALOGUE)
		statuses = {d["status"] for d in result.edges + result.q_matrix + result.merges}
		self.assertEqual(statuses, {"review"})
		self.assertIn({"question": "Q2", "kc": "insert_after_k"}, [{"question": q["question"], "kc": q["kc"]} for q in result.q_matrix])
		self.assertEqual(result.summary()["automatic_share"], 0.0)

	def test_jev_merges_links_and_prunes(self):
		def decide(state, key):
			if key == "same":
				return 0.93  # node_structure == node_structure_basics
			if key == "requires":
				return 0.9 if state["prerequisite"]["key"] == "node_structure" else 0.05
			return 0.95 if (state["item"]["question"], key) in {("Chèn sau k", "insert_after_k"), ("Node gồm những trường nào?", "node_structure")} else 0.1

		judge = FakeJev(decide)
		result = build_knowledge_map(COURSE, llm=None, judge=judge, catalogue=CATALOGUE)
		self.assertNotIn("node_structure_basics", result.components)
		accepted_edges = {(e["from"], e["to"]) for e in result.edges if e["status"] == "accepted"}
		self.assertEqual(accepted_edges, {("node_structure", "insert_after_k")})
		accepted_links = {(q["question"], q["kc"]) for q in result.q_matrix if q["status"] == "accepted"}
		self.assertEqual(accepted_links, {("Q1", "node_structure"), ("Q2", "insert_after_k")})
		self.assertEqual(result.summary()["automatic_share"], 1.0)

	def test_cycles_are_broken(self):
		catalogue = [
			{"key": "a", "label": "A", "description": "", "prerequisites": ["b"], "lessons": ["L1"], "questions": []},
			{"key": "b", "label": "B", "description": "", "prerequisites": ["a"], "lessons": ["L2"], "questions": []},
		]
		judge = FakeJev(lambda state, key: 0.95 if key == "requires" else 0.0)
		result = build_knowledge_map(COURSE, llm=None, judge=judge, catalogue=catalogue)
		accepted = [e for e in result.edges if e["status"] == "accepted"]
		self.assertEqual(len(accepted), 1)

	def test_course_wide_proposal_parses_one_catalogue(self):
		reply = (
			'```json\n[{"key": "Node Structure", "label": "Cấu trúc node", "lessons": ["L1", "L9"], "questions": ["Q1", "Q9"]},'
			' {"key": "node_structure", "label": "trùng", "lessons": ["L2"]},'
			' {"label": "Chèn sau k", "prerequisites": ["node structure"], "lessons": ["L2"], "questions": ["Q2"]}]\n```'
		)
		catalogue = propose_components(FakeLLM(reply), COURSE)
		self.assertEqual([c["key"] for c in catalogue], ["node_structure", "chen_sau_k"])
		self.assertEqual(catalogue[0]["lessons"], ["L1"])
		self.assertEqual(catalogue[0]["questions"], ["Q1"])
		self.assertEqual(catalogue[1]["prerequisites"], ["node_structure"])

	def test_jev_error_degrades_to_fallback(self):
		def broken(url, payload, headers, timeout):
			raise TimeoutError("slow")

		answers = ask_safely(JevJudge("k", post=broken), {"x": 1}, {"q": noul("?")})
		self.assertIsNone(answers["q"].value)
		self.assertEqual(answers["q"].source, "fallback:TimeoutError")


if __name__ == "__main__":
	unittest.main()
