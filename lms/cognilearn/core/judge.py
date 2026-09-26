"""Semantic judgments (Jev System One) with a deterministic fallback.

Jev answers narrow questions with probabilities; it never selects pedagogical actions from
numbers (that is policy code). Every judgment carries its distribution so it can be logged.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from lms.cognilearn.core.contracts import Judgment

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

Poster = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]


def _urllib_post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
	request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
	with urllib.request.urlopen(request, timeout=timeout) as response:
		return json.loads(response.read().decode())


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict[str, Any]:
	question: dict[str, Any] = {"type": "noul", "instructions": instructions}
	if true and false:
		question["criteria"] = {"true": true, "false": false}
	return question


def choice(instructions: str, options: dict[str, str]) -> dict[str, Any]:
	return {"type": "choice", "instructions": instructions, "criteria": options}


class JevJudge:
	source = "jev"

	def __init__(
		self,
		api_key: str,
		*,
		url: str = JEV_URL,
		model: str = JEV_MODEL,
		timeout: int = 30,
		post: Poster | None = None,
	):
		self.api_key = api_key
		self.url = url
		self.model = model
		self.timeout = timeout
		self.post = post or _urllib_post

	@property
	def available(self) -> bool:
		return bool(self.api_key)

	def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Judgment]:
		"""Ask independent questions about one state in a single request."""
		payload = {"state": state, "model": self.model, "questions": questions}
		headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
		response = self.post(self.url, payload, headers, self.timeout)
		return {key: _to_judgment(key, answer) for key, answer in (response.get("answers") or {}).items()}


class FallbackJudge:
	"""Used when Jev is not configured or fails: every question comes back unanswered."""

	source = "fallback"
	available = False

	def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Judgment]:
		return {
			key: Judgment(question=key, value=None, source=self.source, accepted=False) for key in questions
		}


def _to_judgment(key: str, answer: dict[str, Any]) -> Judgment:
	kind = answer.get("type")
	if kind == "noul":
		probability = float(answer.get("noul") or 0.0)
		return Judgment(
			question=key,
			value=probability,
			probabilities={"true": probability, "false": 1 - probability},
			source="jev",
		)
	if kind == "choice":
		return Judgment(
			question=key,
			value=answer.get("choice"),
			probabilities=answer.get("probabilities") or {},
			confidence=answer.get("confidence"),
			source="jev",
		)
	return Judgment(
		question=key,
		value=answer.get("score"),
		probabilities=answer.get("probabilities") or {},
		confidence=answer.get("confidence"),
		source="jev",
	)


def ask_safely(judge, state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Judgment]:
	"""Jev failures degrade to the fallback instead of breaking the learner's request."""
	if not getattr(judge, "available", False):
		return FallbackJudge().ask(state, questions)
	try:
		return judge.ask(state, questions)
	except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
		answers = FallbackJudge().ask(state, questions)
		for judgment in answers.values():
			judgment.source = f"fallback:{type(error).__name__}"
		return answers


def route(probability: float | None, accept_at: float, reject_at: float) -> str:
	"""Confidence routing: auto-accept, auto-reject, or send to the teacher queue."""
	if probability is None:
		return "review"
	if probability >= accept_at:
		return "accepted"
	if probability <= reject_at:
		return "rejected"
	return "review"
