"""Deterministic evaluator for constrained exercises. Never executes learner code."""

from __future__ import annotations

import re
from typing import Any

from lms.cognilearn.core.contracts import Evaluation

EVALUATOR_VERSION = "deterministic_sll_evaluator_v2"
ITEM_TYPES = {"mcq", "tracing", "pointer_order"}
STAGES = {"baseline", "guided_practice", "independent_checkpoint", "delayed_recheck"}


def _normalize_key(value: Any) -> str:
	text = str(value or "").strip()
	if len(text) > 1 and text[0].upper() in "ABCDE" and text[1] in ".):":
		return text[0].upper()
	if text.isdigit() and int(text) < 5:
		return chr(ord("A") + int(text))
	return text.upper()


def _compact(value: Any) -> str:
	text = str(value or "").lower().replace("```cpp", "").replace("```", "")
	return re.sub(r"[^a-z0-9_>\-]+", "", text)


def _statements(answer: str) -> tuple[str, ...]:
	return tuple(part for part in (_compact(piece) for piece in re.split(r"[;\n]", str(answer or ""))) if part)


def _response_text(item: dict[str, Any], response: Any) -> str:
	"""A pointer_order response may arrive as a list of option keys in the learner's order."""
	if isinstance(response, list | tuple):
		by_key = {option["key"]: option["text"] for option in item.get("options") or []}
		return "; ".join(by_key.get(str(key), str(key)) for key in response)
	return str(response or "").strip()


def evaluate(item: dict[str, Any], response: Any) -> Evaluation:
	mode = item.get("answer_mode") or "option"
	submitted = _response_text(item, response)
	correct = str(item.get("correct_answer") or "")

	if mode == "option":
		is_correct = _normalize_key(submitted) == _normalize_key(correct)
	elif mode == "ordered_tokens":
		# Compare statement by statement. The cycle-2 token scan accepted the wrong order
		# "node_k->next = new_node; new_node->next = node_k->next" because both tokens also
		# appear, in order, inside the second statement.
		accepted = {_statements(answer) for answer in item.get("accepted_answers") or []}
		is_correct = _statements(submitted) in accepted
	else:
		accepted = {_compact(answer) for answer in item.get("accepted_answers") or []} or {_compact(correct)}
		is_correct = _compact(submitted) in accepted

	misconception = None
	if not is_correct:
		misconception = (item.get("misconception_by_answer") or {}).get(_normalize_key(submitted))
		if not misconception:
			codes = item.get("misconception_codes") or []
			misconception = codes[0] if codes else None

	return Evaluation(
		is_correct=is_correct,
		correct_answer=correct,
		answer_mode=mode,
		misconception_code=misconception,
	)


def hint_for_item(item: dict[str, Any], hints_used: int = 0) -> str | None:
	"""Next reviewed scaffold. Repeated requests stay on the last level; the answer is never revealed."""
	ladder = item.get("hint_ladder") or []
	if not ladder:
		return None
	level = max(0, int(hints_used or 0))
	return str(ladder[min(level, len(ladder) - 1)])


def public_item(item: dict[str, Any]) -> dict[str, Any]:
	"""What the browser may see: no answer, accepted answers or misconception map."""
	return {
		"code": item["code"],
		"stage": item["stage"],
		"item_type": item["item_type"],
		"stem": item["stem"],
		"options": item.get("options") or [],
		"has_hints": bool(item.get("hint_ladder")),
	}


def validate_items(items: list[dict[str, Any]], target_concept: str) -> list[str]:
	errors: list[str] = []
	seen: set[str] = set()
	for item in items:
		code = str(item.get("code") or "")
		if not code or code in seen:
			errors.append(f"duplicate_or_missing_code:{code}")
		seen.add(code)
		if item.get("stage") not in STAGES:
			errors.append(f"wrong_stage:{code}")
		if item.get("item_type") not in ITEM_TYPES:
			errors.append(f"wrong_type:{code}")
		if target_concept not in (item.get("concepts") or []):
			errors.append(f"missing_target_concept:{code}")
		if not item.get("correct_answer"):
			errors.append(f"missing_answer:{code}")
		if item.get("item_type") in {"mcq", "pointer_order"} and len(item.get("options") or []) < 2:
			errors.append(f"too_few_options:{code}")
	return errors
