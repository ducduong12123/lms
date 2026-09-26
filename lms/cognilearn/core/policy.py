"""PT5: versioned pedagogical rules for the pilot (ported from CogniLearn ``pilot_policy``).

The Agentic condition observes -> diagnoses -> sequences -> replans. The Fixed condition
keeps the same content in a frozen order so the comparison stays credible.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Sequence
from typing import Any

from lms.cognilearn.core.content_sll import STUDY_ID, TARGET_CONCEPT, item_codes_for_stage
from lms.cognilearn.core.contracts import Condition, Diagnosis, Plan, ReplanDecision

POLICY_VERSION = "agentic_pilot_policy_v2"
CHECKPOINT_PROMOTE = 0.8
CHECKPOINT_REGRESS = 0.5
GUIDED_CONTINUE = 0.5
RECHECK_DELAY_HOURS = 72


def assign_condition(enrollment_index: int, study_id: str = STUDY_ID) -> Condition:
	"""Deterministic permuted blocks of four (two per condition)."""
	block_index, slot = divmod(max(0, int(enrollment_index)), 4)
	block = [Condition.AGENTIC, Condition.AGENTIC, Condition.FIXED, Condition.FIXED]
	seed = int(hashlib.sha256(f"{study_id}:block:{block_index}".encode()).hexdigest(), 16)
	random.Random(seed).shuffle(block)
	return block[slot]


def build_diagnosis(attempts: Sequence[dict[str, Any]]) -> Diagnosis:
	rows = list(attempts)
	correct = sum(1 for row in rows if row.get("correct") is True)
	wrong = [row for row in rows if row.get("correct") is not True]
	misconceptions = Counter(str(row["misconception_code"]) for row in wrong if row.get("misconception_code"))
	gaps = Counter(str(tag) for row in wrong for tag in row.get("prerequisites") or [] if tag)
	summary = (
		"Mình sẽ tập trung vào phép chèn sau vị trí k, đặc biệt là cách giữ successor và thứ tự liên kết."
		if misconceptions
		else "Mình sẽ kiểm tra lại phép chèn sau vị trí k bằng sơ đồ và đoạn mã ngắn, rồi để bạn tự làm checkpoint."
	)
	return Diagnosis(
		target_concept=TARGET_CONCEPT,
		baseline_accuracy=round(correct / len(rows), 3) if rows else 0.0,
		confidence=round(min(0.95, 0.4 + 0.12 * min(len(rows), 4)), 3) if rows else 0.25,
		misconception_codes=[code for code, _ in misconceptions.most_common(3)],
		prerequisite_gaps=[code for code, _ in gaps.most_common(3)],
		evidence_item_codes=[str(row.get("item_code")) for row in rows if row.get("item_code")],
		summary_for_student=summary,
	)


_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def order_items(
	items: Sequence[dict[str, Any]], *, stage: str, condition: Condition, diagnosis: Diagnosis | None
) -> list[dict[str, Any]]:
	"""Agentic puts items matching observed misconceptions and gaps first; Fixed keeps manifest order."""
	candidates = [item for item in items if item.get("stage") == stage]
	manifest = {code: index for index, code in enumerate(item_codes_for_stage(stage))}

	def base(item):
		return (manifest.get(item["code"], 999), item["code"])

	if condition == Condition.FIXED or diagnosis is None:
		return sorted(candidates, key=base)

	misconception_rank = {code: index for index, code in enumerate(diagnosis.misconception_codes)}
	gap_rank = {code: index for index, code in enumerate(diagnosis.prerequisite_gaps)}

	def rank(item):
		matched = [misconception_rank[c] for c in item.get("misconception_codes") or [] if c in misconception_rank]
		gaps = [gap_rank[t] for t in item.get("prerequisites") or [] if t in gap_rank]
		return (
			min(matched, default=99),
			min(gaps, default=99),
			_DIFFICULTY_RANK.get(item.get("difficulty") or "medium", 1),
			*base(item),
		)

	return sorted(candidates, key=rank)


def build_plan(condition: Condition, diagnosis: Diagnosis, items: Sequence[dict[str, Any]]) -> Plan:
	def codes(stage):
		return [item["code"] for item in order_items(items, stage=stage, condition=condition, diagnosis=diagnosis)]

	agentic = condition == Condition.AGENTIC
	return Plan(
		study_id=STUDY_ID,
		condition=condition,
		target_concept=TARGET_CONCEPT,
		diagnosis=diagnosis,
		guided_item_codes=codes("guided_practice"),
		checkpoint_item_codes=codes("independent_checkpoint"),
		recheck_item_codes=codes("delayed_recheck"),
		rationale_for_researcher=(
			"Agentic ưu tiên biến thể gắn với misconception quan sát được rồi kiểm tra bằng item mới."
			if agentic
			else "Fixed giữ nguyên thứ tự và độ khó định trước cho mọi người học."
		),
		decision_source="agentic_policy" if agentic else "fixed_policy",
		policy_version=POLICY_VERSION,
	)


def build_replan(
	condition: Condition,
	attempts: Sequence[dict[str, Any]],
	checkpoint_accuracy: float | None = None,
) -> ReplanDecision:
	rows = list(attempts)
	guided = [row for row in rows if row.get("mode") == "guided"]
	guided_accuracy = sum(1 for row in guided if row.get("correct") is True) / len(guided) if guided else None
	evidence = [str(row.get("item_code")) for row in rows if row.get("item_code")][-8:]

	if condition == Condition.FIXED:
		action, reason = "schedule_recheck", "Phần luyện tập đã xong; hệ thống hẹn bài kiểm tra lại sau khoảng ba ngày."
	elif checkpoint_accuracy is not None:
		if checkpoint_accuracy >= CHECKPOINT_PROMOTE:
			action, reason = "schedule_recheck", "Checkpoint đã đạt ngưỡng; hệ thống hẹn bài kiểm tra lại sau khoảng ba ngày."
		elif checkpoint_accuracy < CHECKPOINT_REGRESS:
			action, reason = "regress", "Checkpoint còn nhiều lỗi; hãy quay lại sơ đồ và liên kết successor trước."
		else:
			action, reason = "continue", "Bạn đã tiến bộ nhưng chưa ổn định; hãy xem lại một lần trước khi kiểm tra lại."
	elif guided_accuracy is not None and guided_accuracy < GUIDED_CONTINUE:
		action, reason = "continue_guided", "Lỗi liên kết vẫn lặp lại; hãy làm thêm một biến thể có gợi ý từng bước."
	else:
		action, reason = "move_to_checkpoint", "Bạn đã có đủ tín hiệu luyện tập; hãy thử checkpoint mới không có gợi ý."

	return ReplanDecision(
		next_action=action,
		reason_for_student=reason,
		evidence_item_codes=evidence,
		source="agentic_policy" if condition == Condition.AGENTIC else "fixed_policy",
		policy_version=POLICY_VERSION,
	)
