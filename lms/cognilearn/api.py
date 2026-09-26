"""Whitelisted endpoints for the CogniLearn exercise block, learner state and knowledge map."""

from __future__ import annotations

import json

import frappe

from lms.cognilearn.adapters import events, repository
from lms.cognilearn.core import evaluator
from lms.lms.utils import has_course_instructor_role, has_moderator_role


def _require_login() -> str:
	if frappe.session.user == "Guest":
		frappe.throw("Please log in to practise.", frappe.PermissionError)
	return frappe.session.user


def _require_teacher() -> None:
	if not (has_moderator_role() or has_course_instructor_role() or "System Manager" in frappe.get_roles()):
		frappe.throw("Only teachers can do this.", frappe.PermissionError)


@frappe.whitelist()
def get_items(codes: str | list) -> list[dict]:
	"""Items as the browser may see them: no answer key, no misconception map."""
	_require_login()
	codes = json.loads(codes) if isinstance(codes, str) else codes
	return [evaluator.public_item(repository.get_item(code)) for code in codes if frappe.db.exists("CL Item", code)]


@frappe.whitelist(methods=["POST"])
def submit_attempt(
	code: str,
	response: str | list,
	hints_used: int = 0,
	latency_ms: int | None = None,
	lesson: str | None = None,
	course: str | None = None,
) -> dict:
	member = _require_login()
	item = repository.get_item(code)
	if isinstance(response, str) and response.startswith("["):
		response = json.loads(response)
	if lesson:
		course = frappe.db.get_value("Course Lesson", lesson, "course")
	elif course and not frappe.db.exists("LMS Course", course):
		course = None
	outcome = repository.record_attempt(
		member=member,
		item=item,
		response=response,
		hints_used=int(hints_used or 0),
		latency_ms=int(latency_ms) if latency_ms else None,
		lesson=lesson,
		course=course,
	)
	result = outcome["evaluation"]
	reply = {"correct": result.is_correct, "mode": outcome["mode"], "attempt": outcome["attempt"]}
	# Answers are only revealed on practice items; assessment items stay closed for the study.
	if item["stage"] == "guided_practice" and result.is_correct is False:
		reply["next_hint"] = evaluator.hint_for_item(item, int(hints_used or 0))
	return reply


@frappe.whitelist()
def get_hint(code: str, hints_used: int = 0) -> dict:
	_require_login()
	item = repository.get_item(code)
	if item["stage"] != "guided_practice":
		return {"hint": None, "reason": "Bài này là bài tự làm nên không có gợi ý."}
	return {"hint": evaluator.hint_for_item(item, int(hints_used or 0)), "level": int(hints_used or 0) + 1}


@frappe.whitelist()
def my_state() -> dict:
	return repository.learner_state(_require_login())


@frappe.whitelist()
def get_knowledge_map(course: str) -> dict:
	_require_teacher()
	components = frappe.get_all(
		"CL Knowledge Component", filters={"course": course}, fields=["name", "kc_key", "label", "description"]
	)
	edges = frappe.get_all(
		"CL Knowledge Edge",
		filters={"course": course},
		fields=["name", "prerequisite", "dependent", "status", "probability", "source", "origin"],
	)
	links = frappe.get_all(
		"CL Item Map",
		filters={"course": course},
		fields=["name", "question", "question_doctype", "knowledge_component", "status", "probability", "source"],
	)
	runs = frappe.get_all(
		"CL Knowledge Map Run",
		filters={"course": course},
		fields=["name", "status", "judge_source", "automatic_share", "summary", "error", "creation"],
		order_by="creation desc",
		limit=1,
	)
	return {"components": components, "edges": edges, "links": links, "last_run": runs[0] if runs else None}


@frappe.whitelist(methods=["POST"])
def run_knowledge_map(course: str) -> dict:
	_require_teacher()
	events.enqueue_mapping(course, force=True)
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
def review_decision(doctype: str, name: str, status: str) -> dict:
	"""Teacher confirms or rejects a queued edge or question link; the mapper will not overwrite it."""
	_require_teacher()
	if doctype not in {"CL Item Map", "CL Knowledge Edge"} or status not in {"Accepted", "Rejected"}:
		frappe.throw("Invalid review.")
	frappe.db.set_value(doctype, name, {"status": status, "source": "teacher"})
	return {"name": name, "status": status}


@frappe.whitelist(methods=["POST"])
def seed_pilot_items() -> dict:
	frappe.only_for("System Manager")
	return {"items": repository.seed_pilot_items()}
