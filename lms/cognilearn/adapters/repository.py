"""Frappe persistence for the CogniLearn core: settings, items, evidence, knowledge maps."""

from __future__ import annotations

import html
import json
import re
from typing import Any

import frappe
from frappe.utils import get_datetime, now_datetime

from lms.cognilearn.core import content_sll, elo, evaluator
from lms.cognilearn.core.judge import FallbackJudge, JevJudge
from lms.cognilearn.core.knowledge_map import MAPPER_VERSION, KnowledgeMap
from lms.cognilearn.core.llm import LLMClient
from lms.lms.utils import get_editorjs_blocks

EXERCISE_BLOCK = "cognilearnExercise"


def settings():
	return frappe.get_cached_doc("CL Settings")


def _password(field: str) -> str:
	return settings().get_password(field, raise_exception=False) or ""


def get_judge():
	key = _password("jev_api_key")
	return JevJudge(key, model=settings().jev_model or "jev-latest") if key else FallbackJudge()


def get_llm() -> LLMClient:
	config = settings()
	if not config.llm_base_url:
		frappe.throw("Set the LLM Base URL in CL Settings before mapping knowledge.")
	return LLMClient(config.llm_base_url, _password("llm_api_key"), config.llm_model)


# ---- items ---------------------------------------------------------------------------------


def seed_pilot_items() -> int:
	"""Upsert the frozen linked-list pilot items; returns how many were written."""
	for item in content_sll.items():
		values = {
			"study_id": item["study_id"],
			"stage": item["stage"],
			"item_type": item["item_type"],
			"difficulty": item["difficulty"],
			"stem": item["stem"],
			"content": json.dumps(item, ensure_ascii=False),
			"content_version": item["content_version"],
		}
		if frappe.db.exists("CL Item", item["code"]):
			frappe.db.set_value("CL Item", item["code"], values)
		else:
			frappe.get_doc({"doctype": "CL Item", "code": item["code"], **values}).insert(ignore_permissions=True)
	return len(content_sll.ITEMS)


def get_item(code: str) -> dict[str, Any]:
	content = frappe.db.get_value("CL Item", code, "content")
	if not content:
		frappe.throw(f"Unknown CogniLearn item {code}", frappe.DoesNotExistError)
	return json.loads(content) if isinstance(content, str) else content


# ---- evidence and learner model -------------------------------------------------------------


def record_attempt(
	*,
	member: str,
	item: dict[str, Any],
	response: Any,
	hints_used: int,
	latency_ms: int | None,
	lesson: str | None,
	course: str | None,
) -> dict[str, Any]:
	result = evaluator.evaluate(item, response)
	# Any hint turns the attempt into guided evidence, whatever the stage.
	mode = "guided" if item["stage"] == "guided_practice" or hints_used else "independent"
	attempt = frappe.db.count("CL Evidence", {"member": member, "item": item["code"]}) + 1
	frappe.get_doc(
		{
			"doctype": "CL Evidence",
			"member": member,
			"item": item["code"],
			"course": course,
			"lesson": lesson,
			"stage": item["stage"],
			"mode": mode,
			"correct": int(result.is_correct),
			"misconception_code": result.misconception_code,
			"hints_used": hints_used,
			"latency_ms": latency_ms,
			"attempt": attempt,
			"weight": elo.evidence_weight(mode),
			"concepts": json.dumps(item["concepts"]),
			"response": json.dumps(response, ensure_ascii=False),
			"evaluator_version": evaluator.EVALUATOR_VERSION,
			"model_version": elo.MODEL_VERSION,
		}
	).insert(ignore_permissions=True)
	return {"evaluation": result, "mode": mode, "attempt": attempt}


def learner_state(member: str) -> dict[str, Any]:
	rows = frappe.get_all(
		"CL Evidence",
		filters={"member": member},
		fields=["item", "correct", "mode", "weight", "concepts", "creation"],
		order_by="creation asc",
	)
	difficulty = dict(frappe.get_all("CL Item", fields=["name", "difficulty"], as_list=True))
	evidence = [
		{
			"item_code": row.item,
			"difficulty": difficulty.get(row.item),
			"concepts": json.loads(row.concepts or "[]"),
			"correct": bool(row.correct),
			"mode": row.mode,
			"weight": row.weight,
			"at": get_datetime(row.creation),
		}
		for row in rows
	]
	states, _ratings = elo.replay(evidence)
	now = now_datetime()
	half_life = float(settings().half_life_days or elo.DEFAULT_HALF_LIFE_DAYS)
	concepts = []
	for key, state in sorted(states.items()):
		mastery = elo.decayed_mastery(state, now, half_life)
		concepts.append(
			{
				"concept": key,
				"label": content_sll.KNOWLEDGE_COMPONENTS.get(key, key),
				"elo": round(state.elo, 1),
				"mastery": mastery,
				"raw_mastery": elo.mastery_percent(state.elo),
				"confidence": state.confidence,
				"attempts": state.attempts,
				"state": elo.state_label(state, mastery),
			}
		)
	return {"model_version": elo.MODEL_VERSION, "evidence_count": len(evidence), "concepts": concepts}


# ---- course snapshot for knowledge mapping --------------------------------------------------


def _plain(html_or_md: str | None) -> str:
	text = re.sub(r"<[^>]+>", " ", str(html_or_md or ""))
	return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _question(name: str) -> dict[str, Any] | None:
	doc = frappe.db.get_value("LMS Question", name, ["name", "question", "type", *[f"option_{i}" for i in range(1, 11)]], as_dict=True)
	if not doc:
		return None
	options = [_plain(doc[f"option_{i}"]) for i in range(1, 11) if doc.get(f"option_{i}")]
	return {"id": doc.name, "doctype": "LMS Question", "text": _plain(doc.question), "options": options}


def course_snapshot(course: str) -> dict[str, Any]:
	"""Course -> ordered lessons with text and every question the lessons embed."""
	course_doc = frappe.get_doc("LMS Course", course)
	lessons = []
	for chapter_row in course_doc.chapters:
		chapter = frappe.get_doc("Course Chapter", chapter_row.chapter)
		for lesson_row in chapter.lessons:
			lesson = frappe.get_doc("Course Lesson", lesson_row.lesson)
			text_parts, questions, quizzes = [_plain(lesson.body)], [], set(filter(None, [lesson.quiz_id]))
			for block in get_editorjs_blocks(lesson.content):
				data = block.get("data") or {}
				kind = block.get("type")
				if kind == "quiz" and data.get("quiz"):
					quizzes.add(data["quiz"])
				elif kind == EXERCISE_BLOCK:
					for code in data.get("items") or []:
						if frappe.db.exists("CL Item", code):
							item = get_item(code)
							questions.append({"id": code, "doctype": "CL Item", "text": item["stem"], "options": [o["text"] for o in item["options"]]})
				else:
					text_parts.append(_plain(data.get("text") or data.get("code") or ""))
			for quiz in quizzes:
				for row in frappe.get_all("LMS Quiz Question", filters={"parent": quiz}, fields=["question"], order_by="idx"):
					question = _question(row.question)
					if question:
						questions.append(question)
			lessons.append({"id": lesson.name, "title": lesson.title, "text": " ".join(filter(None, text_parts)), "questions": questions})
	return {"name": course, "title": course_doc.title, "lessons": lessons}


def save_knowledge_map(course: str, result: KnowledgeMap, snapshot: dict[str, Any]) -> None:
	"""Replace the course's machine decisions; rows a teacher already edited are kept."""
	for doctype in ("CL Item Map", "CL Knowledge Edge"):
		for name in frappe.get_all(doctype, filters={"course": course, "source": ["!=", "teacher"]}, pluck="name"):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	names: dict[str, str] = {}
	for component in result.components.values():
		existing = frappe.db.get_value("CL Knowledge Component", {"course": course, "kc_key": component["key"]})
		values = {
			"label": component["label"],
			"description": component["description"],
			"lessons": json.dumps(component["lessons"]),
			"mapper_version": MAPPER_VERSION,
		}
		if existing:
			frappe.db.set_value("CL Knowledge Component", existing, values)
			names[component["key"]] = existing
		else:
			doc = frappe.get_doc({"doctype": "CL Knowledge Component", "course": course, "kc_key": component["key"], **values})
			names[component["key"]] = doc.insert(ignore_permissions=True).name
	# Concepts from earlier runs that this run no longer proposes go, unless a teacher-reviewed row uses them.
	kept_by_teacher = set(
		frappe.get_all("CL Item Map", filters={"course": course}, pluck="knowledge_component")
		+ frappe.get_all("CL Knowledge Edge", filters={"course": course}, pluck="prerequisite")
		+ frappe.get_all("CL Knowledge Edge", filters={"course": course}, pluck="dependent")
	)
	current = set(names.values())
	for stale in frappe.get_all("CL Knowledge Component", filters={"course": course}, pluck="name"):
		if stale not in current and stale not in kept_by_teacher:
			frappe.delete_doc("CL Knowledge Component", stale, ignore_permissions=True, force=True)
	status_label = {"accepted": "Accepted", "rejected": "Rejected", "review": "Review"}
	for edge in result.edges:
		frappe.get_doc(
			{
				"doctype": "CL Knowledge Edge",
				"course": course,
				"prerequisite": names[edge["from"]],
				"dependent": names[edge["to"]],
				"status": status_label[edge["status"]],
				"probability": edge["p"],
				"source": edge["source"],
				"origin": edge["origin"],
			}
		).insert(ignore_permissions=True)
	doctype_of = {q["id"]: q["doctype"] for lesson in snapshot["lessons"] for q in lesson["questions"]}
	for link in result.q_matrix:
		frappe.get_doc(
			{
				"doctype": "CL Item Map",
				"course": course,
				"question": link["question"],
				"question_doctype": doctype_of.get(link["question"], "LMS Question"),
				"knowledge_component": names[link["kc"]],
				"status": status_label[link["status"]],
				"probability": link["p"],
				"source": link["source"],
			}
		).insert(ignore_permissions=True)
