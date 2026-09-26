"""Step hints (help level 2): the LLM writes a first step, Jev alone decides whether it may be shown.

Generation and judgment are separate: the LLM proposes; Jev answers three narrow questions
about the proposal (does it give the answer away, is it consistent with the worked solution,
does it point at the concept the question tests). Code routes on the probabilities. A hint is
shown only if every check passes; otherwise the learner's ladder skips to the solution. No Jev,
no step hint: an unverified hint is never shown.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from lms.cognilearn.core.judge import ask_safely, noul

# v2: the leak question asks exactly what the prompt forbids (v1 also rejected hints that
# name the method, which for one-step questions is every useful hint); plain-text replies.
HINT_VERSION = "step_hint_v2"
MAX_GENERATIONS = 2
LEAK_MAX = 0.2
FAITHFUL_MIN = 0.8
ON_CONCEPT_MIN = 0.8

SYSTEM = """Bạn là trợ giảng. Viết MỘT gợi ý "bước đầu tiên" cho một câu hỏi luyện tập, bằng tiếng Việt.
Yêu cầu:
- Tối đa 2 câu, xưng "bạn".
- Chỉ ra nên bắt đầu từ đâu: công thức, định nghĩa hay cách nhìn vấn đề cần dùng.
- KHÔNG nêu đáp án, KHÔNG tính ra kết quả cuối, KHÔNG nói lựa chọn nào đúng hay sai.
- Không nhắc lại toàn bộ đề. Không dùng LaTeX hay Markdown; viết công thức bằng chữ thường, ví dụ z = (x − trung bình) / độ lệch chuẩn.
Chỉ trả về đúng câu gợi ý, không thêm tiêu đề hay giải thích."""


@dataclass
class HintResult:
	text: str | None
	status: str  # Accepted | Rejected
	p_leak: float | None = None
	p_faithful: float | None = None
	p_on_concept: float | None = None
	judge_source: str = ""
	attempts: list[dict[str, Any]] = field(default_factory=list)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


def _prompt(item: dict[str, Any], feedback: str | None) -> str:
	lines = [
		f"Câu hỏi: {item['question']}",
		f"Các lựa chọn: {'; '.join(item.get('options') or []) or '(tự điền)'}",
		f"Khái niệm câu này kiểm tra: {', '.join(item.get('concepts') or []) or '(chưa rõ)'}",
		f"Đáp án đúng (chỉ để bạn hiểu, không được lộ): {', '.join(item.get('correct') or [])}",
	]
	if item.get("solution"):
		lines.append(f"Lời giải (chỉ để bạn hiểu, không được lộ): {item['solution']}")
	if feedback:
		lines.append(f"Gợi ý trước bị loại vì: {feedback}. Viết lại cho khắc phục điều đó.")
	return "\n".join(lines)


def _questions() -> dict[str, dict[str, Any]]:
	return {
		"leaks": noul(
			"Does `hint` give away the answer to `question`?",
			true="The hint states the final answer or its value, carries out the calculation to the result, "
			"or says which option is correct or which options are wrong.",
			false="The hint only says where to start (a definition, formula or way of looking at the "
			"problem); the learner still has to apply it to reach the answer.",
		),
		"faithful": noul(
			"Is `hint` correct and consistent with `correct_answer` and `solution`, so a learner who "
			"follows it is led toward the correct answer rather than a wrong one?"
		),
		"on_concept": noul(
			"Does `hint` direct the learner to the idea in `concepts` that `question` requires, "
			"as a useful first step?"
		),
	}


def _failure(p_leak, p_faithful, p_on_concept) -> str | None:
	if p_leak is None or p_faithful is None or p_on_concept is None:
		return "không kiểm chứng được"
	if p_leak > LEAK_MAX:
		return "lộ đáp án hoặc gần như lộ"
	if p_faithful < FAITHFUL_MIN:
		return "có thể sai hoặc dẫn tới đáp án sai"
	if p_on_concept < ON_CONCEPT_MIN:
		return "không hướng vào đúng khái niệm cần dùng"
	return None


def _hint_text(reply: str) -> str:
	"""Plain text as asked; tolerate a JSON object or a fenced block if the model adds one."""
	text = re.sub(r"^\s*```(?:json|text)?\s*|\s*```\s*$", "", reply.strip(), flags=re.I).strip()
	if text.startswith("{"):
		try:
			text = str(json.loads(text).get("hint") or "")
		except (ValueError, AttributeError):
			return ""
	return text.strip().strip('"').strip()


def generate_step_hint(llm, judge, item: dict[str, Any]) -> HintResult:
	"""item = {question, options, correct, solution, concepts} as plain text."""
	attempts: list[dict[str, Any]] = []
	feedback = None
	source = ""
	for _ in range(MAX_GENERATIONS):
		try:
			text = _hint_text(llm.chat(SYSTEM, _prompt(item, feedback)))
		except Exception as error:  # the LLM is an external service: a bad reply is a rejection
			attempts.append({"text": None, "error": type(error).__name__})
			continue
		if not text:
			attempts.append({"text": None, "error": "empty"})
			continue
		state = {
			"question": item["question"],
			"options": item.get("options") or [],
			"correct_answer": item.get("correct") or [],
			"solution": item.get("solution") or "",
			"concepts": item.get("concepts") or [],
			"hint": text,
		}
		answers = ask_safely(judge, state, _questions())
		p_leak, p_faithful, p_on_concept = (answers[k].value for k in ("leaks", "faithful", "on_concept"))
		source = answers["leaks"].source
		feedback = _failure(p_leak, p_faithful, p_on_concept)
		attempts.append(
			{
				"text": text,
				"p_leak": p_leak,
				"p_faithful": p_faithful,
				"p_on_concept": p_on_concept,
				"failure": feedback,
			}
		)
		if feedback is None:
			return HintResult(text, "Accepted", p_leak, p_faithful, p_on_concept, source, attempts)
		if source != "jev":
			break  # without Jev nothing can pass; do not spend another generation
	last = next((a for a in reversed(attempts) if a.get("text")), {})
	return HintResult(
		last.get("text"),
		"Rejected",
		last.get("p_leak"),
		last.get("p_faithful"),
		last.get("p_on_concept"),
		source,
		attempts,
	)
