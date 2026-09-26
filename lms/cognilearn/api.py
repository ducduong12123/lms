"""Whitelisted endpoints for the CogniLearn exercise block, learner state and knowledge map."""

from __future__ import annotations

import json

import frappe

from lms.cognilearn.adapters import events, repository, study
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
	return [
		evaluator.public_item(repository.get_item(code))
		for code in codes
		if frappe.db.exists("CL Item", code)
	]


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
		"CL Knowledge Component",
		filters={"course": course},
		fields=["name", "kc_key", "label", "description"],
	)
	edges = frappe.get_all(
		"CL Knowledge Edge",
		filters={"course": course},
		fields=["name", "prerequisite", "dependent", "status", "probability", "source", "origin"],
	)
	links = frappe.get_all(
		"CL Item Map",
		filters={"course": course},
		fields=[
			"name",
			"question",
			"question_doctype",
			"knowledge_component",
			"status",
			"probability",
			"source",
		],
	)
	runs = frappe.get_all(
		"CL Knowledge Map Run",
		filters={"course": course},
		fields=["name", "status", "judge_source", "automatic_share", "summary", "error", "creation"],
		order_by="creation desc",
		limit=1,
	)
	questions = {}
	for link in links:
		if link.question not in questions:
			question = (
				repository._question(link.question) if link.question_doctype == "LMS Question" else None
			)
			questions[link.question] = question["text"] if question else link.question
	return {
		"components": components,
		"edges": edges,
		"links": links,
		"questions": questions,
		"course_title": frappe.db.get_value("LMS Course", course, "title"),
		"last_run": runs[0] if runs else None,
	}


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


# ---- adaptive study (any subject) ------------------------------------------------------------


def _study(course: str):
	found = study.active_study(course)
	if not found:
		frappe.throw("This course has no active CogniLearn study.", frappe.DoesNotExistError)
	return found


@frappe.whitelist()
def study_status(course: str) -> dict:
	member = _require_login()
	found = study.active_study(course)
	view = study.student_view(found, member) if found else {"study": False}
	return {**view, "course_title": frappe.db.get_value("LMS Course", course, "title")}


@frappe.whitelist(methods=["POST"])
def start_practice(course: str) -> dict:
	member = _require_login()
	found = _study(course)
	if not study.baseline_done(found, member):
		frappe.throw("Take the baseline quiz first.")
	participant = study.ensure_participant(found, member)
	if participant.status == "Practising" and not study.open_set(participant):
		study.plan_next_set(found, participant)
	return {
		**study.student_view(found, member),
		"course_title": frappe.db.get_value("LMS Course", course, "title"),
	}


@frappe.whitelist(methods=["POST"])
def answer_practice(course: str, question: str, answer: str | list) -> dict:
	member = _require_login()
	found = _study(course)
	participant = study.ensure_participant(found, member)
	practice_set = study.open_set(participant)
	if not practice_set:
		frappe.throw("You have no open practice set.")
	if isinstance(answer, str) and answer.startswith("["):
		answer = json.loads(answer)
	return study.answer_practice(found, participant, practice_set, question, answer)


@frappe.whitelist()
def study_overview(course: str) -> dict:
	"""Teacher view: participants and their progress, never mixed into the student API."""
	_require_teacher()
	found = _study(course)
	participants = frappe.get_all(
		"CL Study Participant",
		filters={"study": found.name},
		fields=["name", "member", "condition", "status", "recheck_due_at", "enrollment_index"],
		order_by="enrollment_index asc",
	)
	for row in participants:
		row.sets_done = frappe.db.count("CL Practice Set", {"participant": row.name, "status": "Done"})
	return {
		"study": found.as_dict(),
		"participants": participants,
		"pool_size": len(study.practice_pool(found)),
		"graph": study.course_graph(course),
	}


@frappe.whitelist(methods=["POST"])
def run_leak_gate(course: str) -> dict:
	_require_teacher()
	return study.run_leak_gate(_study(course))


@frappe.whitelist()
def course_links(course: str) -> dict:
	"""Which CogniLearn pages this user can open for a course (nothing for plain courses)."""
	if frappe.session.user == "Guest":
		return {"practice": False, "map": False}
	teacher = has_moderator_role() or has_course_instructor_role() or "System Manager" in frappe.get_roles()
	return {
		"practice": bool(study.active_study(course)),
		"map": teacher and bool(frappe.db.exists("CL Knowledge Component", {"course": course})),
	}
