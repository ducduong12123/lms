"""Subject-agnostic adaptive loop: replay evidence, diagnose on the knowledge graph, pick
the next practice set, replan after each set.

Works for any course whose questions the knowledge mapper has linked to KCs (PT0). The
Q-matrix is read at replay time, so a teacher correcting a link re-scores history.

PT3 learner state = Elo (decides) + BKT (shadow, logged only).
PT5 = the versioned rules below; Jev only screens practice questions that would leak a
recheck question (a semantic gate), never picks actions.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from lms.cognilearn.core import bkt, elo
from lms.cognilearn.core.contracts import Condition
from lms.cognilearn.core.judge import ask_safely, noul

ADAPTIVE_VERSION = "graph_adaptive_policy_v2"
# On the Elo scale one independent answer moves a KC only ~2 points from 50%, so absolute
# "mastered" thresholds (70%) cannot be reached inside a pilot session. Diagnosis instead reads
# the sign of the evidence: below 50% = more failure than success, 55%+ = clearly positive.
WEAK_BELOW = 50.0
SOLID_AT = 55.0
TARGET_SUCCESS = 0.7
ADVANCE_AT = 0.8
REGRESS_BELOW = 0.5
LEAK_AT = 0.5


# ---- replay ----------------------------------------------------------------------------------


@dataclass
class Attempt:
	member: str
	question: str
	correct: bool
	at: datetime
	mode: str = "independent"
	weight: float | None = None


@dataclass
class Prediction:
	"""What each model expected before seeing the outcome: the basis of the Elo-vs-BKT test."""

	member: str
	question: str
	correct: bool
	concepts: list[str]
	elo_p: float | None
	bkt_p: float | None


@dataclass
class CourseState:
	elo: dict[str, dict[str, elo.ConceptState]] = field(default_factory=dict)
	bkt: dict[str, dict[str, float]] = field(default_factory=dict)
	item_ratings: dict[str, float] = field(default_factory=dict)
	predictions: list[Prediction] = field(default_factory=list)
	unmapped: int = 0

	def learner(self, member: str) -> dict[str, elo.ConceptState]:
		return self.elo.get(member, {})


def predict_elo(states: dict[str, elo.ConceptState], item_rating: float, concepts: list[str]) -> float | None:
	if not concepts:
		return None
	ability = statistics.fmean(states[c].elo if c in states else elo.START_ELO for c in concepts)
	return elo.expected(ability, item_rating)


def observe(state: CourseState, attempt: Attempt, q_matrix: dict[str, list[str]]) -> Prediction | None:
	"""Predict with both models, then learn from the outcome (in place)."""
	concepts = list(q_matrix.get(attempt.question) or [])
	if not concepts:
		state.unmapped += 1
		return None
	learner = state.elo.setdefault(attempt.member, {})
	known = state.bkt.setdefault(attempt.member, {})
	rating = state.item_ratings.setdefault(attempt.question, elo.START_ELO)
	prediction = Prediction(
		attempt.member,
		attempt.question,
		attempt.correct,
		concepts,
		_round(predict_elo(learner, rating, concepts)),
		_round(bkt.predict(known, concepts)),
	)
	state.predictions.append(prediction)
	elo.apply_attempt(
		learner,
		state.item_ratings,
		item_code=attempt.question,
		difficulty=None,
		concepts=concepts,
		correct=attempt.correct,
		mode=attempt.mode,
		at=attempt.at,
		requested_weight=attempt.weight,
		freeze_item=False,
	)
	bkt.update(known, concepts, attempt.correct)
	return prediction


def replay_course(attempts: Iterable[Attempt], q_matrix: dict[str, list[str]]) -> CourseState:
	"""Every learner of a course in time order, so item ratings learn from all of them."""
	state = CourseState()
	for attempt in sorted(attempts, key=lambda row: row.at):
		observe(state, attempt, q_matrix)
	return state


def _round(value: float | None) -> float | None:
	return None if value is None else round(value, 4)


def mastery_view(
	states: dict[str, elo.ConceptState], now: datetime, half_life_days: float
) -> dict[str, dict[str, Any]]:
	view = {}
	for key, concept in states.items():
		mastery = elo.decayed_mastery(concept, now, half_life_days)
		view[key] = {
			"mastery": mastery,
			"elo": round(concept.elo, 1),
			"confidence": concept.confidence,
			"attempts": concept.attempts,
			"state": elo.state_label(concept, mastery),
		}
	return view


# ---- knowledge graph -------------------------------------------------------------------------


def ancestors(kc: str, edges: Iterable[tuple[str, str]]) -> list[str]:
	"""Transitive prerequisites of ``kc``, deepest (most foundational) first."""
	parents: dict[str, list[str]] = {}
	for prerequisite, dependent in edges:
		parents.setdefault(dependent, []).append(prerequisite)
	depth: dict[str, int] = {}
	frontier, level = [kc], 0
	while frontier:
		level += 1
		nxt = []
		for node in frontier:
			for parent in parents.get(node, []):
				if parent != kc and depth.get(parent, 0) < level:
					depth[parent] = level
					nxt.append(parent)
		frontier = nxt
		if level > 64:  # the mapper enforces a DAG; this only guards hand-edited cycles
			break
	return sorted(depth, key=lambda node: -depth[node])


@dataclass
class GraphDiagnosis:
	focus_kc: str | None
	target_kc: str | None
	prerequisite_gaps: list[str]
	weak_kcs: list[str]
	reason: str  # gap | weak | explore | mastered

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


def diagnose(
	mastery: dict[str, dict[str, Any]],
	edges: list[tuple[str, str]],
	kc_order: list[str],
	*,
	regress_from: str | None = None,
) -> GraphDiagnosis:
	"""Target the KC with the most net-negative evidence; practise its most foundational weak
	prerequisite first if it has one. With no weakness, probe the most advanced
	unseen KC whose prerequisites show no weakness: success there vouches for what lies below."""
	order = {kc: index for index, kc in enumerate(kc_order)}

	def score(kc):
		return mastery.get(kc, {}).get("mastery")

	weak = sorted(
		(kc for kc in kc_order if score(kc) is not None and score(kc) < WEAK_BELOW),
		key=lambda kc: (score(kc), order[kc]),
	)
	if regress_from:
		shaky = [kc for kc in ancestors(regress_from, edges) if score(kc) is None or score(kc) < SOLID_AT]
		shaky.sort(key=lambda kc: (score(kc) if score(kc) is not None else -1.0, order.get(kc, 999)))
		if shaky:
			return GraphDiagnosis(shaky[0], regress_from, shaky, weak, "gap")
		return GraphDiagnosis(regress_from, regress_from, [], weak, "weak")
	if weak:
		target = weak[0]
		gaps = [kc for kc in ancestors(target, edges) if kc in weak]
		if gaps:
			return GraphDiagnosis(gaps[0], target, gaps, weak, "gap")
		return GraphDiagnosis(target, target, [], weak, "weak")
	depth = {kc: len(ancestors(kc, edges)) for kc in kc_order}
	unseen = sorted((kc for kc in kc_order if score(kc) is None), key=lambda kc: (-depth[kc], order[kc]))
	if unseen:
		return GraphDiagnosis(unseen[0], unseen[0], [], [], "explore")
	return GraphDiagnosis(None, None, [], [], "mastered")


# ---- selection -------------------------------------------------------------------------------


@dataclass
class Selection:
	questions: list[str]
	candidates: list[dict[str, Any]]  # scored alternatives, logged for later off-policy analysis


def select_items(
	condition: Condition,
	*,
	pool: list[str],
	q_matrix: dict[str, list[str]],
	history: dict[str, bool],
	learner: dict[str, elo.ConceptState],
	item_ratings: dict[str, float],
	focus_kc: str | None,
	size: int,
) -> Selection:
	"""Fixed: the course order, skipping what was already tried. Agentic: the focus KC,
	unseen questions first, closest to a 70% expected success rate."""
	fresh = [q for q in pool if q not in history]
	if condition == Condition.FIXED or focus_kc is None:
		chosen = fresh[:size]
		return Selection(chosen, [{"question": q, "rank": i} for i, q in enumerate(chosen)])

	order = {q: i for i, q in enumerate(pool)}
	retry = [q for q in pool if history.get(q) is False]

	def scored(questions, tier):
		rows = []
		for question in questions:
			concepts = q_matrix.get(question) or []
			p = predict_elo(learner, item_ratings.get(question, elo.START_ELO), concepts)
			rows.append(
				{
					"question": question,
					"tier": tier,
					"p": _round(p),
					"distance": round(abs((p or 0.5) - TARGET_SUCCESS), 4),
				}
			)
		return rows

	on_focus = [q for q in fresh if focus_kc in (q_matrix.get(q) or [])]
	retry_focus = [q for q in retry if focus_kc in (q_matrix.get(q) or [])]
	others = [q for q in fresh if q not in on_focus]
	# Unmapped questions (still in the teacher's review queue) teach the model nothing: last.
	rows = (
		scored(on_focus, 0)
		+ scored(retry_focus, 1)
		+ scored([q for q in others if q_matrix.get(q)], 2)
		+ scored([q for q in others if not q_matrix.get(q)], 3)
	)
	rows.sort(key=lambda row: (row["tier"], row["distance"], order[row["question"]]))
	return Selection([row["question"] for row in rows[:size]], rows[: size * 3])


# ---- replanning ------------------------------------------------------------------------------


@dataclass
class Replan:
	action: str  # advance | continue | regress | schedule_recheck
	reason_for_student: str
	set_accuracy: float | None
	policy_version: str = ADAPTIVE_VERSION

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


def replan(
	condition: Condition,
	*,
	set_results: list[bool],
	sets_done: int,
	budget_sets: int,
	pool_left: int,
	focus_label: str | None = None,
) -> Replan:
	accuracy = round(sum(set_results) / len(set_results), 3) if set_results else None
	if sets_done >= budget_sets or pool_left == 0:
		return Replan(
			"schedule_recheck",
			"Bạn đã xong phần luyện tập hôm nay. Hệ thống hẹn bài kiểm tra lại sau khoảng ba ngày.",
			accuracy,
		)
	if condition == Condition.FIXED:
		return Replan("continue", "Tiếp tục với các câu tiếp theo của khóa học.", accuracy)
	topic = f" về {focus_label}" if focus_label else ""
	if accuracy is not None and accuracy >= ADVANCE_AT:
		return Replan(
			"advance",
			f"Bạn đã làm chắc phần{topic}. Hệ thống chuyển sang phần bạn còn yếu tiếp theo.",
			accuracy,
		)
	if accuracy is not None and accuracy < REGRESS_BELOW:
		return Replan(
			"regress", f"Phần{topic} còn nhiều lỗi. Hãy củng cố kiến thức nền của nó trước.", accuracy
		)
	return Replan(
		"continue", f"Bạn đang tiến bộ{topic} nhưng chưa ổn định; luyện thêm một lượt nữa.", accuracy
	)


# ---- Jev safety gate -------------------------------------------------------------------------


def find_leaks(
	judge,
	practice: list[dict[str, Any]],
	recheck: list[dict[str, Any]],
	q_matrix: dict[str, list[str]],
) -> list[dict[str, Any]]:
	"""Practice questions that would give away a recheck question sharing a KC with them.
	Returns every judged pair with its probability; ``leak`` marks the ones to exclude."""
	checks = []
	for question in practice:
		kcs = set(q_matrix.get(question["id"]) or [])
		rivals = [r for r in recheck if kcs & set(q_matrix.get(r["id"]) or [])]
		if not rivals:
			continue
		questions = {
			f"leak_{index}": noul(
				"Nếu người học vừa làm câu `practice` (và xem đáp án), họ có thể trả lời câu "
				f"`recheck[{index}]` mà không cần hiểu bài không — vì hai câu gần như cùng đề, "
				"cùng số liệu hoặc cùng đáp án?",
				"Gần như cùng một câu: đáp án của câu luyện tập dùng lại được trực tiếp.",
				"Hai câu khác nhau về số liệu hoặc tình huống; phải tự giải lại.",
			)
			for index, _ in enumerate(rivals)
		}
		state = {"practice": question["text"], "recheck": [r["text"] for r in rivals]}
		answers = ask_safely(judge, state, questions)
		for index, rival in enumerate(rivals):
			judgment = answers.get(f"leak_{index}")
			p = judgment.value if judgment else None
			checks.append(
				{
					"practice": question["id"],
					"recheck": rival["id"],
					"p": p,
					"source": judgment.source if judgment else "none",
					# Without Jev, only an identical text counts as a leak.
					"leak": (p >= LEAK_AT) if p is not None else _same_text(question["text"], rival["text"]),
				}
			)
	return checks


def _same_text(a: str, b: str) -> bool:
	return " ".join(a.lower().split()) == " ".join(b.lower().split())
