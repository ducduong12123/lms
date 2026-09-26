"""Frappe side of the inner-loop help: content for each rung of the ladder, and the job that
writes step hints (LLM) and lets Jev accept or reject them.

    bench --site <site> execute lms.cognilearn.adapters.hints.generate_hints --kwargs '{"course": "<course>"}'
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import frappe

from lms.cognilearn.adapters import repository
from lms.cognilearn.core import hints as step_hints
from lms.cognilearn.core.inner_loop import CONCEPT, SOLUTION, STEP
from lms.lms.doctype.lms_question.lms_question import (
	QUESTION_CORRECTNESS_FIELDS,
	QUESTION_EXPLANATION_FIELDS,
	QUESTION_OPTION_FIELDS,
	QUESTION_POSSIBILITY_FIELDS,
)

WORKERS = 4


# ---- ladder content --------------------------------------------------------------------------


def _answer_key(question: str) -> dict[str, Any]:
	doc = frappe.db.get_value(
		"LMS Question",
		question,
		[
			"question",
			"type",
			*QUESTION_OPTION_FIELDS,
			*QUESTION_CORRECTNESS_FIELDS,
			*QUESTION_EXPLANATION_FIELDS,
			*QUESTION_POSSIBILITY_FIELDS,
		],
		as_dict=True,
	)
	rows = list(
		zip(QUESTION_OPTION_FIELDS, QUESTION_CORRECTNESS_FIELDS, QUESTION_EXPLANATION_FIELDS, strict=True)
	)
	options = [doc[option] for option, _, _ in rows if doc[option]]
	correct = [doc[option] for option, right, _ in rows if doc[option] and doc[right]]
	if doc.type == "User Input":
		correct = [doc[field] for field in QUESTION_POSSIBILITY_FIELDS if doc[field]]
	return {
		"question": repository._plain(doc.question),
		"options": [repository._plain(o) for o in options],
		"correct": [repository._plain(c) for c in correct],
		"solution": " ".join(
			repository._plain(doc[explanation])
			for option, right, explanation in rows
			if doc[option] and doc[right] and doc[explanation]
		),
		"explanations": {
			doc[option]: doc[explanation]
			for option, _, explanation in rows
			if doc[option] and doc[explanation]
		},
	}


def solution(question: str) -> dict[str, Any]:
	key = _answer_key(question)
	return {"correct_answers": key["correct"], "explanation": key["solution"]}


def choice_feedback(question: str, answer: list[str]) -> str | None:
	"""Why the chosen (wrong) option is wrong, without the right answer."""
	explanations = _answer_key(question)["explanations"]
	texts = [explanations[a] for a in answer if a in explanations]
	return " ".join(texts) or None


def _lesson_positions(course: str) -> dict[str, dict[str, Any]]:
	positions = {}
	for chapter_number, chapter in enumerate(
		frappe.get_all("Chapter Reference", filters={"parent": course}, fields=["chapter"], order_by="idx"),
		start=1,
	):
		for lesson_number, row in enumerate(
			frappe.get_all(
				"Lesson Reference", filters={"parent": chapter.chapter}, fields=["lesson"], order_by="idx"
			),
			start=1,
		):
			positions[row.lesson] = {
				"lesson": row.lesson,
				"title": frappe.db.get_value("Course Lesson", row.lesson, "title"),
				"chapter_number": chapter_number,
				"lesson_number": lesson_number,
			}
	return positions


def _home_lesson(question: str) -> str | None:
	"""The lesson whose quiz holds this question (question banks are linked to their lesson)."""
	for quiz in frappe.get_all("LMS Quiz Question", filters={"question": question}, pluck="parent"):
		lesson = frappe.db.get_value("LMS Quiz", quiz, "lesson")
		if lesson:
			return lesson
	return None


def concept_hint(course: str, question: str, concepts: list[str]) -> dict[str, Any] | None:
	"""Level 1: the concepts the question tests (accepted Q-matrix row) and the lesson to revisit."""
	components = [
		frappe.db.get_value("CL Knowledge Component", kc, ["label", "description", "lessons"], as_dict=True)
		for kc in concepts
	]
	components = [c for c in components if c]
	positions = _lesson_positions(course)
	home = _home_lesson(question)
	candidates = [home] if home in positions else []
	for component in components:
		lessons = (
			json.loads(component.lessons or "[]")
			if isinstance(component.lessons, str)
			else component.lessons or []
		)
		candidates += [lesson for lesson in lessons if lesson in positions]
	lesson = positions[candidates[0]] if candidates else None
	if not components and not lesson:
		return None
	return {
		"concepts": [{"label": c.label, "description": c.description or ""} for c in components],
		"lesson": lesson,
	}


def step_hint(question: str) -> str | None:
	return frappe.db.get_value(
		"CL Hint",
		{"question": question, "level": STEP, "status": "Accepted"},
		"text",
		order_by="creation desc",
	)


def ladder(course: str, question: str, concepts: list[str]) -> dict[str, Any]:
	"""Which rungs have content for this question (the content itself is sent only when asked)."""
	return {
		CONCEPT: concept_hint(course, question, concepts),
		STEP: step_hint(question),
		SOLUTION: solution(question),
	}


# ---- step-hint generation ---------------------------------------------------------------------


def _item(question: str, concept_labels: list[str]) -> dict[str, Any]:
	key = _answer_key(question)
	return {
		"question": key["question"],
		"options": key["options"],
		"correct": key["correct"],
		"solution": key["solution"],
		"concepts": concept_labels,
	}


def _hash(item: dict[str, Any]) -> str:
	return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def generate_hints(course: str, force: bool = False) -> dict[str, Any]:
	"""Write a step hint for every practice question whose content or concepts changed."""
	from lms.cognilearn.adapters import study  # study imports this module

	found = study.active_study(course)
	questions = study.practice_pool(found) if found else study.course_questions(course)
	graph = study.course_graph(course)
	todo = []
	for question in questions:
		item = _item(question, [graph["labels"].get(kc, kc) for kc in graph["q_matrix"].get(question, [])])
		digest = _hash(item)
		current = {
			"question": question,
			"question_hash": digest,
			"generator_version": step_hints.HINT_VERSION,
		}
		if not force and frappe.db.exists("CL Hint", current):
			continue
		todo.append((question, item, digest))
	llm, judge = repository.get_llm(), repository.get_judge()
	with ThreadPoolExecutor(max_workers=WORKERS) as pool:
		results = list(pool.map(lambda job: step_hints.generate_step_hint(llm, judge, job[1]), todo))
	summary = {"questions": len(questions), "generated": len(todo), "accepted": 0, "rejected": 0}
	for (question, _item_payload, digest), result in zip(todo, results, strict=True):
		for old in frappe.get_all("CL Hint", filters={"question": question, "level": STEP}, pluck="name"):
			frappe.delete_doc("CL Hint", old, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "CL Hint",
				"course": course,
				"question": question,
				"level": STEP,
				"status": result.status,
				"text": result.text,
				"p_leak": result.p_leak,
				"p_faithful": result.p_faithful,
				"p_on_concept": result.p_on_concept,
				"judge_source": result.judge_source,
				"question_hash": digest,
				"generator_version": step_hints.HINT_VERSION,
				"attempts": json.dumps(result.attempts, ensure_ascii=False),
			}
		).insert(ignore_permissions=True)
		summary["accepted" if result.status == "Accepted" else "rejected"] += 1
	frappe.db.commit()
	return summary


def enqueue_hints(course: str, force: bool = False) -> None:
	frappe.enqueue(
		"lms.cognilearn.adapters.hints.generate_hints",
		queue="long",
		timeout=1800,
		job_id=f"cognilearn-hints-{course}",
		deduplicate=True,
		enqueue_after_commit=True,
		course=course,
		force=force,
	)
