"""Read-only summaries of a running study: prediction scores, mastery bands, arm descriptives.

Pure Python, so the teacher dashboard, the learner's own progress view and the offline
analysis (``research.model_comparison``) all compute the same numbers.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from typing import Any

from lms.cognilearn.core import adaptive

# ---- next-response prediction (Elo vs BKT) ---------------------------------------------------


def auc(pairs: list[tuple[float, int]]) -> float | None:
	positives = [p for p, y in pairs if y]
	negatives = [p for p, y in pairs if not y]
	if not positives or not negatives:
		return None
	wins = sum((p > q) + 0.5 * (p == q) for p in positives for q in negatives)
	return round(wins / (len(positives) * len(negatives)), 4)


def rmse(pairs: list[tuple[float, int]]) -> float | None:
	return round(math.sqrt(sum((p - y) ** 2 for p, y in pairs) / len(pairs)), 4) if pairs else None


def log_loss(pairs: list[tuple[float, int]]) -> float | None:
	if not pairs:
		return None
	eps = 1e-6
	return round(
		-sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in pairs) / len(pairs),
		4,
	)


def score(pairs: list[tuple[float, int]]) -> dict[str, Any]:
	return {"n": len(pairs), "auc": auc(pairs), "rmse": rmse(pairs), "log_loss": log_loss(pairs)}


def compare_logged(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
	"""Score the P(correct) each model logged before the outcome, on rows where both did."""
	both = [r for r in rows if r.get("elo_p") is not None and r.get("bkt_p") is not None]
	return {
		"elo": score([(float(r["elo_p"]), int(r["correct"])) for r in both]),
		"bkt": score([(float(r["bkt_p"]), int(r["correct"])) for r in both]),
	}


# ---- mastery bands (what a learner may see about themselves) ---------------------------------

NONE, SHAKY, GROWING, SOLID = "none", "shaky", "growing", "solid"


def mastery_band(row: dict[str, Any] | None) -> str:
	"""Three coarse bands on the same thresholds the policy diagnoses with, so what the learner
	sees never disagrees with why the system picked their questions."""
	if not row or not row.get("attempts"):
		return NONE
	mastery = float(row["mastery"])
	if mastery < adaptive.WEAK_BELOW:
		return SHAKY
	if mastery < adaptive.SOLID_AT:
		return GROWING
	return SOLID


# ---- arm descriptives ------------------------------------------------------------------------


def mean(values: Iterable[float | None]) -> float | None:
	present = [v for v in values if v is not None]
	return round(statistics.fmean(present), 1) if present else None


def rate(part: int, whole: int) -> float | None:
	return round(100.0 * part / whole, 1) if whole else None


def arm_summary(participants: list[dict[str, Any]]) -> dict[str, Any]:
	"""Descriptive only: the pilot is far too small for a test, and gains mix arms with luck."""
	gains = [
		p["recheck"] - p["baseline"]
		for p in participants
		if p.get("baseline") is not None and p.get("recheck") is not None
	]
	first = sum(p["practice_answers"] for p in participants)
	return {
		"n": len(participants),
		"baseline": mean(p.get("baseline") for p in participants),
		"recheck": mean(p.get("recheck") for p in participants),
		"gain": mean(gains),
		"with_recheck": len(gains),
		"practice_accuracy": rate(sum(p["practice_correct"] for p in participants), first),
		"hint_rate": rate(
			sum(p["hinted_items"] for p in participants), sum(p["items"] for p in participants)
		),
		"lessons_done": mean(p["lessons_done"] for p in participants),
	}
