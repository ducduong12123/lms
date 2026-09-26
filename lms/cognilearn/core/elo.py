"""PT1 + PT3: quality-weighted multidimensional Elo with a Q-mask and forgetting.

Ported from CogniLearn ``mastery_engine`` (quality_weighted_elo_v2). The learner state is
recomputable from the evidence log in order; decay is applied at read time, so stored
ratings never depend on when the replay ran.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

MODEL_VERSION = "quality_weighted_elo_v3_decay"
START_ELO = 1000.0
K_FACTOR = 32.0
ITEM_K_FACTOR = 8.0
RECENT_WINDOW = 5
CONFIDENCE_TARGET_WEIGHT = 8.0
DEFAULT_HALF_LIFE_DAYS = 14.0
GUIDED_DEFAULT_WEIGHT = 0.35
DIFFICULTY_BASE = {"easy": 900.0, "medium": 1000.0, "hard": 1100.0}


def expected(student_elo: float, item_elo: float) -> float:
	return 1.0 / (1.0 + math.pow(10.0, (item_elo - student_elo) / 400.0))


def mastery_percent(elo: float) -> float:
	return round(expected(elo, START_ELO) * 100.0, 1)


def item_base_elo(difficulty: str | None) -> float:
	return DIFFICULTY_BASE.get(str(difficulty or "medium").lower(), START_ELO)


def evidence_weight(mode: str, requested: float | None = None) -> float:
	"""Guided evidence (with hints or scaffolds) can never count like unaided evidence."""
	if mode == "guided":
		return round(max(0.1, min(0.45, GUIDED_DEFAULT_WEIGHT if requested is None else requested)), 3)
	return round(max(0.5, min(1.0, 1.0 if requested is None else requested)), 3)


def q_mask_weight(total_weight: float, concept_count: int) -> float:
	"""Split an item's evidence across the concepts its Q-matrix row marks."""
	return total_weight if concept_count <= 1 else total_weight / math.sqrt(concept_count)


@dataclass
class ConceptState:
	elo: float = START_ELO
	weight_sum: float = 0.0
	attempts: int = 0
	last_independent_at: datetime | None = None
	recent: list[tuple[bool, float]] = field(default_factory=list)

	@property
	def confidence(self) -> float:
		return round(min(1.0, self.weight_sum / CONFIDENCE_TARGET_WEIGHT), 3)


@dataclass
class UpdateRecord:
	concept: str
	expected: float
	weight: float
	elo_before: float
	elo_after: float


def apply_attempt(
	states: dict[str, ConceptState],
	item_ratings: dict[str, float],
	*,
	item_code: str,
	difficulty: str | None,
	concepts: list[str],
	correct: bool,
	mode: str,
	at: datetime,
	requested_weight: float | None = None,
	freeze_item: bool = True,
) -> list[UpdateRecord]:
	"""Update learner and item ratings in place for one attempt; return the audit trail."""
	weight = evidence_weight(mode, requested_weight)
	item_elo = item_ratings.setdefault(item_code, item_base_elo(difficulty))
	outcome = 1.0 if correct else 0.0
	per_concept = q_mask_weight(weight, len(concepts))
	records: list[UpdateRecord] = []
	surprise = 0.0
	for concept in concepts:
		state = states.setdefault(concept, ConceptState())
		probability = expected(state.elo, item_elo)
		before = state.elo
		state.elo = before + K_FACTOR * per_concept * (outcome - probability)
		state.weight_sum += per_concept
		state.attempts += 1
		state.recent = [*state.recent, (correct, weight)][-RECENT_WINDOW:]
		if mode == "independent":
			state.last_independent_at = at
		surprise += outcome - probability
		records.append(
			UpdateRecord(
				concept, round(probability, 4), round(per_concept, 4), round(before, 2), round(state.elo, 2)
			)
		)
	if not freeze_item and concepts:
		item_ratings[item_code] = item_elo - ITEM_K_FACTOR * weight * surprise / len(concepts)
	return records


def decayed_mastery(
	state: ConceptState, now: datetime, half_life_days: float = DEFAULT_HALF_LIFE_DAYS
) -> float:
	"""Mastery used for decisions: drifts back toward the prior (50%) without fresh independent evidence."""
	raw = mastery_percent(state.elo)
	if state.last_independent_at is None or half_life_days <= 0:
		return raw
	days = max(0.0, (now - state.last_independent_at).total_seconds() / 86400.0)
	prior = mastery_percent(START_ELO)
	return round(prior + (raw - prior) * math.pow(0.5, days / half_life_days), 1)


def state_label(state: ConceptState, mastery: float) -> str:
	recent = state.recent
	recent_accuracy = sum(1 for ok, _ in recent if ok) / len(recent) if recent else None
	recent_quality = sum(w for _, w in recent) / len(recent) if recent else 0.0
	if mastery >= 70.0 and state.confidence >= 0.5 and recent_quality >= 0.5:
		return "UNLOCKED"
	if (
		recent_accuracy is not None
		and recent_accuracy >= 0.8
		and len(recent) >= RECENT_WINDOW
		and recent_quality >= 0.5
	):
		return "UNLOCKED_BY_MOMENTUM"
	if state.attempts >= 8 and recent_accuracy is not None and recent_accuracy < 0.4:
		return "HARD_BLOCKED"
	if state.confidence < 0.25:
		return "INSUFFICIENT_EVIDENCE"
	return "LOCKED_NEEDS_PRACTICE"


def replay(
	evidence: list[dict], *, freeze_items: bool = True
) -> tuple[dict[str, ConceptState], dict[str, float]]:
	"""Recompute the learner model from evidence rows ordered by time."""
	states: dict[str, ConceptState] = {}
	ratings: dict[str, float] = {}
	for row in sorted(evidence, key=lambda item: item["at"]):
		apply_attempt(
			states,
			ratings,
			item_code=row["item_code"],
			difficulty=row.get("difficulty"),
			concepts=list(row.get("concepts") or []),
			correct=bool(row["correct"]),
			mode=row["mode"],
			at=row["at"],
			requested_weight=row.get("weight"),
			freeze_item=freeze_items,
		)
	return states, ratings
