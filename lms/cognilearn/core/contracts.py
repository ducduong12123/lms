"""Typed contracts crossing the core boundary.

Only decisions, evidence references and learner-facing text cross it; no model reasoning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Condition(str, Enum):
	AGENTIC = "agentic"
	FIXED = "fixed"


class Stage(str, Enum):
	BASELINE = "baseline"
	REVIEW = "review"
	GUIDED_PRACTICE = "guided_practice"
	INDEPENDENT_CHECKPOINT = "independent_checkpoint"
	DELAYED_RECHECK = "delayed_recheck"


class EvidenceMode(str, Enum):
	GUIDED = "guided"
	INDEPENDENT = "independent"


INDEPENDENT_STAGES = {Stage.BASELINE.value, Stage.INDEPENDENT_CHECKPOINT.value, Stage.DELAYED_RECHECK.value}

NEXT_ACTIONS = ("continue_guided", "move_to_checkpoint", "schedule_recheck", "continue", "regress")


def evidence_mode_for_stage(stage: str) -> EvidenceMode:
	return EvidenceMode.INDEPENDENT if stage in INDEPENDENT_STAGES else EvidenceMode.GUIDED


class _Serializable:
	def to_dict(self) -> dict[str, Any]:
		def convert(value):
			if isinstance(value, Enum):
				return value.value
			if isinstance(value, dict):
				return {key: convert(item) for key, item in value.items()}
			if isinstance(value, list | tuple):
				return [convert(item) for item in value]
			return value

		return convert(asdict(self))


@dataclass
class Evaluation(_Serializable):
	is_correct: bool
	correct_answer: str = ""
	answer_mode: str = "option"
	misconception_code: str | None = None


@dataclass
class Diagnosis(_Serializable):
	target_concept: str
	baseline_accuracy: float
	confidence: float
	misconception_codes: list[str] = field(default_factory=list)
	prerequisite_gaps: list[str] = field(default_factory=list)
	evidence_item_codes: list[str] = field(default_factory=list)
	summary_for_student: str = ""
	decision_source: str = "deterministic"


@dataclass
class Plan(_Serializable):
	study_id: str
	condition: Condition
	target_concept: str
	diagnosis: Diagnosis
	guided_item_codes: list[str]
	checkpoint_item_codes: list[str]
	recheck_item_codes: list[str]
	rationale_for_researcher: str
	decision_source: str
	policy_version: str


@dataclass
class ReplanDecision(_Serializable):
	next_action: str
	reason_for_student: str
	evidence_item_codes: list[str]
	source: str
	policy_version: str


@dataclass
class Judgment(_Serializable):
	"""A semantic judgment with its distribution, kept for the decision log."""

	question: str
	value: Any
	probabilities: dict[str, float] = field(default_factory=dict)
	confidence: float | None = None
	source: str = "fallback"
	accepted: bool = True
