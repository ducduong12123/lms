"""Inner loop: help while the learner works on one practice question.

The outer loop (``adaptive``) picks the next set; this module decides what help a learner may
get inside one question and how much the answer then says about them. Pure Python so the
rules are testable and versioned.

Help ladder (the learner asks, in order; a level with no content is skipped):
  concept  - which knowledge component the question tests, and where the lesson is;
  step     - a question-specific first step (LLM-written, Jev-gated, never the answer);
  solution - the worked explanation and the right answer (bottom-out).

Error feedback: a wrong first answer shows why that choice is wrong, not the right answer,
and allows one retry. The second wrong answer, or asking for the solution, ends the question.

Measurement: only the first answer is evidence about the learner. Hints taken before it
make it guided (lower weight); seeing the solution before answering counts as not knowing.
Retries are for learning and are logged, never scored.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

INNER_LOOP_VERSION = "inner_loop_v1"

CONCEPT, STEP, SOLUTION = "concept", "step", "solution"
LADDER = (CONCEPT, STEP, SOLUTION)
MAX_TRIES = 2

# Evidence weight of a first answer by the highest hint seen before it (see elo.evidence_weight).
GUIDED_WEIGHT = {CONCEPT: 0.45, STEP: 0.3}
SOLUTION_WEIGHT = 0.45  # "I needed the solution" is fair evidence of not knowing, but not a slip

QUICK_SOLUTION_SECONDS = 5.0  # asked for the solution this soon after the previous action
QUICK_RETRY_SECONDS = 3.0  # retried this soon after being told the first answer was wrong


@dataclass
class ItemState:
	"""What happened to one question inside a practice set (stored as JSON on the set)."""

	hints: list[dict[str, Any]] = field(default_factory=list)  # [{"level", "at"}]
	tries: list[dict[str, Any]] = field(default_factory=list)  # [{"answer", "correct", "at"}]
	evidence_recorded: bool = False

	@classmethod
	def from_dict(cls, data: dict[str, Any] | None) -> ItemState:
		data = data or {}
		return cls(
			hints=list(data.get("hints") or []),
			tries=list(data.get("tries") or []),
			evidence_recorded=bool(data.get("evidence_recorded")),
		)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)

	@property
	def levels_seen(self) -> list[str]:
		return [hint["level"] for hint in self.hints]

	@property
	def solved(self) -> bool:
		return any(attempt["correct"] for attempt in self.tries)

	@property
	def finished(self) -> bool:
		return self.solved or len(self.tries) >= MAX_TRIES or SOLUTION in self.levels_seen

	@property
	def first_correct(self) -> bool | None:
		return bool(self.tries[0]["correct"]) if self.tries else None


@dataclass
class Evidence:
	correct: bool
	mode: str  # independent | guided
	weight: float
	hints_used: int
	max_hint: str | None


def next_hint(available: set[str] | list[str], seen: list[str]) -> str | None:
	"""The next rung the learner may climb; levels without content are skipped."""
	for level in LADDER:
		if level in available and level not in seen:
			return level
	return None


def can_answer(item: ItemState) -> bool:
	return not item.finished


def retry_allowed(item: ItemState) -> bool:
	"""After a wrong first answer and before the solution was shown."""
	return bool(item.tries) and not item.finished


def evidence_for_first_answer(item: ItemState, correct: bool) -> Evidence:
	"""Evidence for the learner model from the first answer and the hints seen before it."""
	before = item.levels_seen  # called before the try is appended
	if not before:
		return Evidence(correct, "independent", 1.0, 0, None)
	highest = max(before, key=LADDER.index)
	return Evidence(correct, "guided", GUIDED_WEIGHT[highest], len(before), highest)


def evidence_for_solution_first(item: ItemState) -> Evidence:
	"""The learner opened the solution without answering: record not knowing, softly."""
	return Evidence(False, "guided", SOLUTION_WEIGHT, len(item.levels_seen) + 1, SOLUTION)


def _seconds(later: str, earlier: str) -> float:
	return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()


def gaming_flags(item: ItemState) -> list[str]:
	"""Help-seeking patterns worth analysing (logged only, never used to block the learner)."""
	flags: list[str] = []
	events = sorted(
		[(h["at"], "hint", h["level"]) for h in item.hints]
		+ [(t["at"], "try", bool(t["correct"])) for t in item.tries]
	)
	for (previous_at, previous_kind, previous_value), (at, kind, value) in zip(
		events, events[1:], strict=False
	):
		gap = _seconds(at, previous_at)
		if kind == "hint" and value == SOLUTION and gap < QUICK_SOLUTION_SECONDS:
			flags.append("quick_solution")
		if kind == "try" and previous_kind == "try" and previous_value is False and gap < QUICK_RETRY_SECONDS:
			flags.append("quick_retry")
	if item.hints and item.hints[0]["level"] == SOLUTION and not item.tries:
		flags.append("solution_without_trying")
	return sorted(set(flags))
