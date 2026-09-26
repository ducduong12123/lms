"""Bayesian Knowledge Tracing, run in shadow next to Elo for the offline comparison.

BKT never drives a decision. For every attempt the engine logs what BKT would have
predicted before the outcome was known, so the two models can be compared prospectively
(AUC on next-response prediction) at the end of the pilot.

Parameters are the conventional defaults, fixed and versioned before the pilot; fitting
them per KC needs far more data than a pilot yields (and is unidentifiable on little data).
An item marking several KCs is treated conjunctively: every KC must be applied correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

BKT_VERSION = "bkt_standard_v1_conjunctive"


@dataclass(frozen=True)
class Params:
	p_init: float = 0.3
	p_learn: float = 0.1
	p_guess: float = 0.2
	p_slip: float = 0.1


DEFAULT = Params()


def p_correct_one(p_known: float, params: Params = DEFAULT) -> float:
	return p_known * (1 - params.p_slip) + (1 - p_known) * params.p_guess


def predict(known: dict[str, float], concepts: list[str], params: Params = DEFAULT) -> float | None:
	"""P(correct) for an item before its outcome is seen; None when the item maps to no KC."""
	if not concepts:
		return None
	probability = 1.0
	for concept in concepts:
		probability *= p_correct_one(known.get(concept, params.p_init), params)
	return probability


def update(known: dict[str, float], concepts: list[str], correct: bool, params: Params = DEFAULT) -> None:
	"""Posterior on each marked KC given the outcome, then the learning transition (in place)."""
	for concept in concepts:
		prior = known.get(concept, params.p_init)
		if correct:
			hit = prior * (1 - params.p_slip)
			posterior = hit / (hit + (1 - prior) * params.p_guess)
		else:
			miss = prior * params.p_slip
			posterior = miss / (miss + (1 - prior) * (1 - params.p_guess))
		known[concept] = posterior + (1 - posterior) * params.p_learn
