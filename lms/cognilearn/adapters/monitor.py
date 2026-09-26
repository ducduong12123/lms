"""Read-only views of a running study: the teacher's monitor and a learner's own progress.

Nothing here writes. Numbers are recomputed from the evidence log on each call (the pilot is
small), with the same replay the policy uses, so the dashboard never drifts from decisions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import frappe
from frappe.utils import now_datetime

from lms.cognilearn.adapters import hints, repository, study
from lms.cognilearn.core import adaptive, elo, inner_loop, monitor
from lms.cognilearn.core.contracts import Condition

SOURCES = ("quiz", "practice", "recheck")


def _mastery(course: str, graph: dict[str, Any]) -> tuple[adaptive.CourseState, dict[str, dict]]:
	state = study.course_state(course, graph["q_matrix"])
	half_life = float(repository.settings().half_life_days or elo.DEFAULT_HALF_LIFE_DAYS)
	now = now_datetime()
	views = {member: adaptive.mastery_view(learner, now, half_life) for member, learner in state.elo.items()}
	return state, views


def _first_percentage(quiz: str | None, member: str) -> float | None:
	"""Score of the first submission: a retake must not inflate the baseline or the recheck."""
	if not quiz:
		return None
	rows = frappe.get_all(
		"LMS Quiz Submission",
		filters={"quiz": quiz, "member": member},
		fields=["percentage"],
		order_by="creation asc",
		limit=1,
	)
	return round(float(rows[0].percentage or 0), 1) if rows else None


def _behaviour(participant: str) -> dict[str, Any]:
	"""Help-seeking inside practice sets, from the stored inner-loop states."""
	flags: Counter[str] = Counter()
	items = hinted = solution_first = retried = 0
	for row in frappe.get_all(
		"CL Practice Set", filters={"participant": participant}, fields=["item_states"]
	):
		for raw in (study._json(row.item_states) or {}).values():
			item = inner_loop.ItemState.from_dict(raw)
			if not item.hints and not item.tries:
				continue
			items += 1
			first_try = item.tries[0]["at"] if item.tries else None
			before = [h for h in item.hints if first_try is None or h["at"] <= first_try]
			hinted += bool(before)
			solution_first += any(h["level"] == inner_loop.SOLUTION for h in before)
			retried += len(item.tries) > 1
			flags.update(inner_loop.gaming_flags(item))
	return {
		"items": items,
		"hinted_items": hinted,
		"solution_first": solution_first,
		"retried": retried,
		"flags": dict(flags),
	}


def _participants(found, lessons: list[str], positions: dict[str, dict]) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"CL Study Participant",
		filters={"study": found.name},
		fields=["name", "member", "condition", "status", "recheck_due_at", "enrollment_index"],
		order_by="enrollment_index asc",
	)
	result = []
	for row in rows:
		done = [lesson for lesson in lessons if study.lesson_done(row, lesson)]
		current = next((lesson for lesson in lessons if lesson not in done), None)
		practice = frappe.get_all(
			"CL Evidence",
			filters={"member": row.member, "course": found.course, "source": "practice"},
			fields=["correct", "creation"],
			order_by="creation asc",
		)
		last = frappe.get_all(
			"CL Evidence",
			filters={"member": row.member, "course": found.course},
			fields=["creation"],
			order_by="creation desc",
			limit=1,
		)
		result.append(
			{
				**row,
				"full_name": frappe.db.get_value("User", row.member, "full_name") or row.member,
				"lessons_done": len(done),
				"current_lesson": positions.get(current, {}).get("title") if current else None,
				"sets_done": frappe.db.count("CL Practice Set", {"participant": row.name, "status": "Done"}),
				"baseline": _first_percentage(found.baseline_quiz, row.member),
				"recheck": _first_percentage(found.recheck_quiz, row.member),
				"practice_answers": len(practice),
				"practice_correct": sum(1 for r in practice if r.correct),
				"last_active": last[0].creation if last else None,
				**_behaviour(row.name),
			}
		)
	return result


def _models(course: str) -> dict[str, Any]:
	rows = frappe.get_all(
		"CL Evidence",
		filters={"course": course, "item_doctype": "LMS Question"},
		fields=["source", "mode", "correct", "elo_p", "bkt_p"],
	)
	return {
		"all": monitor.compare_logged(rows),
		"independent": monitor.compare_logged(
			[r for r in rows if (r.mode or "independent") == "independent"]
		),
		**{source: monitor.compare_logged([r for r in rows if r.source == source]) for source in SOURCES},
	}


def _recent_decisions(course: str, limit: int = 12) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"CL Decision Log",
		filters={"course": course},
		fields=["name", "member", "condition", "kind", "action", "reason", "policy_version", "creation"],
		order_by="creation desc",
		limit=limit,
	)
	for row in rows:
		row.full_name = frappe.db.get_value("User", row.member, "full_name") or row.member
	return rows


def _concept_order(found, graph: dict[str, Any]) -> list[str]:
	"""Concepts in the order the course teaches them: by their first practice lesson. The
	baseline and recheck quizzes touch most concepts, so they must not count as where one starts."""
	rank = {lesson: index for index, lesson in enumerate(study.practice_lessons(found))}
	first = {}
	for row in frappe.get_all(
		"CL Knowledge Component", filters={"course": found.course}, fields=["name", "lessons"]
	):
		lessons = study._json(row.lessons) or []
		first[row.name] = min((rank[lesson] for lesson in lessons if lesson in rank), default=len(rank))
	position = {kc: index for index, kc in enumerate(graph["order"])}
	return sorted(graph["order"], key=lambda kc: (first.get(kc, len(rank)), position[kc]))


def study_dashboard(found) -> dict[str, Any]:
	"""Everything the teacher's monitor shows for one study."""
	course = found.course
	graph = study.course_graph(course)
	positions = hints._lesson_positions(course)
	lessons = study.practice_lessons(found)
	participants = _participants(found, lessons, positions)
	_, mastery = _mastery(course, graph)
	hint_status = Counter(frappe.get_all("CL Hint", filters={"course": course}, pluck="status"))
	return {
		"course_title": frappe.db.get_value("LMS Course", course, "title"),
		"study": {
			"name": found.name,
			"study_id": found.study_id,
			"set_size": found.set_size,
			"budget_sets": found.budget_sets,
			"recheck_delay_hours": found.recheck_delay_hours,
			"baseline_quiz": found.baseline_quiz,
			"recheck_quiz": found.recheck_quiz,
		},
		"lessons": [positions.get(lesson, {"lesson": lesson}) for lesson in lessons],
		"participants": participants,
		"arms": {
			arm.value: monitor.arm_summary([p for p in participants if p["condition"] == arm.value])
			for arm in Condition
		},
		"concepts": [
			{"name": kc, "label": graph["labels"].get(kc, kc)} for kc in _concept_order(found, graph)
		],
		"mastery": {
			p["member"]: {
				kc: {**row, "band": monitor.mastery_band(row)}
				for kc, row in mastery.get(p["member"], {}).items()
			}
			for p in participants
		},
		"models": _models(course),
		"hints": dict(hint_status),
		"decisions": _recent_decisions(course),
		"policy_version": adaptive.ADAPTIVE_VERSION,
		"model_version": study.MODEL_VERSION,
	}


def learner_progress(found, member: str) -> list[dict[str, Any]]:
	"""A learner's own concepts in three coarse bands. Identical in both arms (it is part of
	the shared interface, not of the adaptive treatment) and never shows raw ratings."""
	graph = study.course_graph(found.course)
	_, mastery = _mastery(found.course, graph)
	own = mastery.get(member, {})
	return [
		{"name": kc, "label": graph["labels"].get(kc, kc), "band": monitor.mastery_band(own.get(kc))}
		for kc in _concept_order(found, graph)
	]
