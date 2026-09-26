"""PT0: build the knowledge map and Q-matrix automatically from a course.

The LLM proposes knowledge components (generation). Jev verifies each merge, prerequisite
edge and question-to-concept link (judgment with a probability). Code prunes candidates,
keeps the graph acyclic and routes each decision: accepted, rejected, or teacher review.
Without Jev, every LLM proposal goes to review.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from lms.cognilearn.core.judge import ask_safely, noul, route
from lms.cognilearn.core.llm import parse_json

MAPPER_VERSION = "knowledge_map_v1"
ACCEPT_AT = 0.8
REJECT_AT = 0.2
MERGE_SIMILARITY = 0.34

MAX_ALL_CANDIDATES = 15

PROPOSE_SYSTEM = "Bạn là chuyên gia thiết kế chương trình. Bạn tách một khóa học thành các khái niệm kiến thức nhỏ, kiểm tra được."
PROPOSE_PROMPT = """Dựa trên toàn bộ khóa học dưới đây, lập MỘT danh mục chung gồm {low}-{high} khái niệm kiến thức
(knowledge component) mà khóa học dạy hoặc đòi hỏi. Mỗi khái niệm chỉ xuất hiện một lần dù nhiều bài dùng nó.
Mỗi khái niệm là một kỹ năng mà người học có thể nắm hoặc chưa nắm độc lập với các khái niệm khác;
tách hai kỹ năng nếu một người học có thể làm đúng kỹ năng này mà vẫn sai kỹ năng kia.
Không tạo hai mục trùng nghĩa hoặc chỉ khác cách diễn đạt.
Trả về DUY NHẤT một JSON array, mỗi phần tử:
{{"key": "snake_case_tieng_anh_khong_dau", "label": "tên ngắn tiếng Việt", "description": "một câu mô tả",
  "prerequisites": ["key khác trong danh mục cần học trước"], "lessons": ["id bài dạy hoặc dùng khái niệm"],
  "questions": ["id câu hỏi đo khái niệm này"]}}
Chỉ dùng id bài và id câu hỏi có trong dữ liệu. Không thêm markdown.

Khóa học: {course}
Các bài (theo thứ tự): {lessons}"""


@dataclass
class KnowledgeMap:
	course: str
	components: dict[str, dict[str, Any]] = field(default_factory=dict)
	edges: list[dict[str, Any]] = field(default_factory=list)
	q_matrix: list[dict[str, Any]] = field(default_factory=list)
	merges: list[dict[str, Any]] = field(default_factory=list)
	judge_source: str = "fallback"
	version: str = MAPPER_VERSION

	def to_dict(self) -> dict[str, Any]:
		return {
			"course": self.course,
			"version": self.version,
			"judge_source": self.judge_source,
			"components": list(self.components.values()),
			"edges": self.edges,
			"q_matrix": self.q_matrix,
			"merges": self.merges,
		}

	def summary(self) -> dict[str, Any]:
		decisions = self.edges + self.q_matrix + self.merges
		counts = {status: sum(1 for d in decisions if d["status"] == status) for status in ("accepted", "rejected", "review")}
		counts["total"] = len(decisions)
		counts["automatic_share"] = round((counts["accepted"] + counts["rejected"]) / len(decisions), 3) if decisions else 0.0
		return counts


def slug(text: str) -> str:
	ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
	return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:60] or "concept"


def _tokens(component: dict[str, Any]) -> set[str]:
	return {token for token in slug(f"{component['key']} {component['label']}").split("_") if len(token) > 1}


def similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
	left, right = _tokens(a), _tokens(b)
	return len(left & right) / len(left | right) if left and right else 0.0


def question_state(question: dict[str, Any]) -> dict[str, Any]:
	return {"question": question.get("text"), "options": question.get("options") or []}


def propose_components(llm, course: dict[str, Any]) -> list[dict[str, Any]]:
	"""One course-wide catalogue, so the same concept gets one key across lessons."""
	lessons = course.get("lessons") or []
	payload = [
		{
			"id": lesson["id"],
			"title": lesson.get("title"),
			"text": str(lesson.get("text") or "")[:1500],
			"questions": [{"id": q["id"], "text": q.get("text"), "options": q.get("options") or []} for q in lesson.get("questions") or []],
		}
		for lesson in lessons
	]
	low = max(3, min(8, len(lessons)))
	prompt = PROPOSE_PROMPT.format(low=low, high=low + 4, course=course.get("title", ""), lessons=payload)
	raw = parse_json(llm.chat(PROPOSE_SYSTEM, prompt))
	lesson_ids = {lesson["id"] for lesson in lessons}
	question_ids = {q["id"] for lesson in lessons for q in lesson.get("questions") or []}
	catalogue: dict[str, dict[str, Any]] = {}
	for entry in raw if isinstance(raw, list) else []:
		if not isinstance(entry, dict) or not str(entry.get("label") or "").strip():
			continue
		key = slug(entry.get("key") or entry["label"])
		catalogue.setdefault(
			key,
			{
				"key": key,
				"label": str(entry["label"]).strip(),
				"description": str(entry.get("description") or "").strip(),
				"prerequisites": [slug(p) for p in entry.get("prerequisites") or [] if str(p).strip()],
				"lessons": [lesson for lesson in entry.get("lessons") or [] if lesson in lesson_ids],
				"questions": [q for q in entry.get("questions") or [] if q in question_ids],
			},
		)
	return list(catalogue.values())


def _creates_cycle(edges: list[tuple[str, str]], new: tuple[str, str]) -> bool:
	graph: dict[str, set[str]] = {}
	for source, target in [*edges, new]:
		graph.setdefault(source, set()).add(target)
	stack, seen = [new[1]], set()
	while stack:
		node = stack.pop()
		if node == new[0]:
			return True
		if node not in seen:
			seen.add(node)
			stack.extend(graph.get(node, ()))
	return False


def build_knowledge_map(
	course: dict[str, Any],
	*,
	llm,
	judge,
	catalogue: list[dict[str, Any]] | None = None,
	accept_at: float = ACCEPT_AT,
	reject_at: float = REJECT_AT,
) -> KnowledgeMap:
	"""``course`` = {"name", "title", "lessons": [{"id", "title", "text", "questions": [...]}] in course order}."""
	result = KnowledgeMap(course=course.get("name") or course.get("title") or "")
	result.judge_source = "jev" if getattr(judge, "available", False) else "fallback"
	lessons = course.get("lessons") or []
	catalogue = catalogue if catalogue is not None else propose_components(llm, course)
	lesson_of_question = {q["id"]: lesson["id"] for lesson in lessons for q in lesson.get("questions") or []}

	# 1. Components from the course-wide catalogue; a concept's lessons include those of its questions.
	for entry in catalogue:
		from_questions = [lesson_of_question[q] for q in entry.get("questions", []) if q in lesson_of_question]
		result.components[entry["key"]] = {
			"key": entry["key"],
			"label": entry["label"],
			"description": entry.get("description", ""),
			"lessons": list(dict.fromkeys([*entry.get("lessons", []), *from_questions])),
		}

	# 2. Merge near-duplicates the catalogue still contains, after a same-concept judgment.
	alias: dict[str, str] = {}
	keys = list(result.components)
	pairs = [
		(a, b)
		for i, a in enumerate(keys)
		for b in keys[i + 1 :]
		if similarity(result.components[a], result.components[b]) >= MERGE_SIMILARITY
	]
	for a, b in pairs:
		if a in alias or b in alias:
			continue
		answers = ask_safely(
			judge,
			{"concept_a": result.components[a], "concept_b": result.components[b]},
			{
				"same": noul(
					"Do `concept_a` and `concept_b` describe the same learnable knowledge component, "
					"so a learner who masters one has mastered the other?"
				)
			},
		)
		judgment = answers["same"]
		status = route(judgment.value, accept_at, reject_at)
		result.merges.append({"keep": a, "drop": b, "p": judgment.value, "status": status, "source": judgment.source})
		if status == "accepted":
			alias[b] = a

	def canonical(key: str) -> str:
		return alias.get(key, key)

	for dropped, kept_key in alias.items():
		merged = result.components.pop(dropped)
		result.components[kept_key]["lessons"] = list(dict.fromkeys(result.components[kept_key]["lessons"] + merged["lessons"]))

	lesson_components: dict[str, list[str]] = {}
	for key, component in result.components.items():
		for lesson_id in component["lessons"]:
			lesson_components.setdefault(lesson_id, []).append(key)

	# 3. Prerequisite edges: catalogue-proposed ones plus previous-lesson -> next-lesson candidates.
	candidates: dict[tuple[str, str], str] = {}
	for entry in catalogue:
		for prerequisite in entry.get("prerequisites", []):
			if prerequisite in result.components or prerequisite in alias:
				candidates.setdefault((canonical(prerequisite), canonical(entry["key"])), "llm")
	for previous, current in zip(lessons, lessons[1:], strict=False):
		for before in lesson_components.get(previous["id"], []):
			for after in lesson_components.get(current["id"], []):
				candidates.setdefault((before, after), "course_order")

	scored = []
	for (source, target), origin in candidates.items():
		if source == target:
			continue
		answers = ask_safely(
			judge,
			{"prerequisite": result.components[source], "dependent": result.components[target]},
			{"requires": noul("Must a learner understand `prerequisite` before they can learn `dependent`?")},
		)
		judgment = answers["requires"]
		if judgment.value is None and origin == "course_order":
			continue  # without a judge, course order alone is too weak to queue for review
		status = route(judgment.value, accept_at, reject_at)
		scored.append({"from": source, "to": target, "p": judgment.value, "status": status, "source": judgment.source, "origin": origin})

	kept: list[tuple[str, str]] = []
	for edge in sorted(scored, key=lambda e: -(e["p"] or 0.0)):
		if edge["status"] != "rejected" and _creates_cycle(kept, (edge["from"], edge["to"])):
			edge["status"], edge["origin"] = "rejected", f"{edge['origin']}:cycle"
		elif edge["status"] != "rejected":
			kept.append((edge["from"], edge["to"]))
		result.edges.append(edge)

	# 4. Q-matrix. A small catalogue makes every concept a candidate; a larger one is pruned to
	#    the lesson's concepts plus their direct prerequisites.
	proposed = {(q, canonical(entry["key"])) for entry in catalogue for q in entry.get("questions", [])}
	all_keys = list(result.components)
	for lesson in lessons:
		own = lesson_components.get(lesson["id"], [])
		prerequisites = [source for source, target in kept if target in own]
		concepts = all_keys if len(all_keys) <= MAX_ALL_CANDIDATES else list(dict.fromkeys(own + prerequisites))
		if not concepts:
			continue
		for question in lesson.get("questions") or []:
			answers = ask_safely(
				judge,
				{"item": question_state(question), "concepts": {k: result.components[k] for k in concepts}},
				{
					k: noul(
						f"Does answering `item` correctly require the knowledge component `concepts.{k}`?",
						true="Solving the item uses this concept.",
						false="The item can be solved without this concept.",
					)
					for k in concepts
				},
			)
			for concept in concepts:
				judgment = answers[concept]
				if judgment.value is None:
					if (question["id"], concept) not in proposed:
						continue
					status = "review"
				else:
					status = route(judgment.value, accept_at, reject_at)
				result.q_matrix.append(
					{"question": question["id"], "kc": concept, "p": judgment.value, "status": status, "source": judgment.source}
				)
	return result
