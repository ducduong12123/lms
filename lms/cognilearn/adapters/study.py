"""Frappe side of the subject-agnostic adaptive loop.

Evidence comes from two places: every native LMS quiz submission (baseline, lesson quizzes,
the delayed recheck) and the adaptive practice sets. Both are LMS Questions, so any course
whose questions the knowledge mapper linked to KCs can run the study.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from lms.cognilearn.adapters import repository
from lms.cognilearn.core import adaptive, bkt, elo, policy
from lms.cognilearn.core.contracts import Condition
from lms.lms.doctype.lms_question.lms_question import (
	QUESTION_CORRECTNESS_FIELDS,
	QUESTION_EXPLANATION_FIELDS,
	QUESTION_OPTION_FIELDS,
)
from lms.lms.doctype.lms_quiz.lms_quiz import check_input_answers, verify_answer

MODEL_VERSION = f"{elo.MODEL_VERSION}+{bkt.BKT_VERSION}"


# ---- course graph and pool -------------------------------------------------------------------


def course_graph(course: str) -> dict[str, Any]:
	"""Accepted knowledge graph and Q-matrix. Teacher-accepted and auto-accepted rows count;
	rows still in review do not, so an unreviewed link never moves a learner's state."""
	lesson_rank = {row["id"]: index for index, row in enumerate(_ordered_lessons(course))}
	components = frappe.get_all(
		"CL Knowledge Component", filters={"course": course}, fields=["name", "label", "lessons", "creation"]
	)

	def first_lesson(component):
		lessons = (
			json.loads(component.lessons or "[]")
			if isinstance(component.lessons, str)
			else component.lessons or []
		)
		return min((lesson_rank.get(lesson, 999) for lesson in lessons), default=999)

	components.sort(key=lambda c: (first_lesson(c), c.creation))
	edges = frappe.get_all(
		"CL Knowledge Edge",
		filters={"course": course, "status": "Accepted"},
		fields=["prerequisite", "dependent"],
	)
	q_matrix: dict[str, list[str]] = {}
	for link in frappe.get_all(
		"CL Item Map",
		filters={"course": course, "status": "Accepted"},
		fields=["question", "knowledge_component"],
		order_by="creation asc",
	):
		q_matrix.setdefault(link.question, []).append(link.knowledge_component)
	return {
		"order": [c.name for c in components],
		"labels": {c.name: c.label for c in components},
		"edges": [(e.prerequisite, e.dependent) for e in edges],
		"q_matrix": q_matrix,
	}


def _ordered_lessons(course: str) -> list[dict[str, Any]]:
	lessons = []
	for chapter in frappe.get_all(
		"Chapter Reference", filters={"parent": course}, fields=["chapter"], order_by="idx"
	):
		for row in frappe.get_all(
			"Lesson Reference", filters={"parent": chapter.chapter}, fields=["lesson"], order_by="idx"
		):
			lessons.append({"id": row.lesson})
	return lessons


def quiz_questions(quiz: str | None) -> list[str]:
	if not quiz:
		return []
	return frappe.get_all("LMS Quiz Question", filters={"parent": quiz}, pluck="question", order_by="idx")


def course_questions(course: str) -> list[str]:
	"""Every auto-gradable LMS Question the course embeds, in course order, once each."""
	seen: dict[str, None] = {}
	for lesson in repository.course_snapshot(course)["lessons"]:
		for question in lesson["questions"]:
			if question["doctype"] == "LMS Question":
				seen.setdefault(question["id"], None)
	types = (
		dict(
			frappe.get_all(
				"LMS Question", filters={"name": ["in", list(seen)]}, fields=["name", "type"], as_list=True
			)
		)
		if seen
		else {}
	)
	return [q for q in seen if types.get(q) in ("Choices", "User Input")]


def practice_pool(study) -> list[str]:
	held_out = set(quiz_questions(study.baseline_quiz)) | set(quiz_questions(study.recheck_quiz))
	excluded = set(_json(study.excluded_questions) or [])
	return [q for q in course_questions(study.course) if q not in held_out and q not in excluded]


# ---- evidence --------------------------------------------------------------------------------


def course_state(course: str, q_matrix: dict[str, list[str]]) -> adaptive.CourseState:
	rows = frappe.get_all(
		"CL Evidence",
		filters={"course": course, "item_doctype": "LMS Question"},
		fields=["member", "item", "correct", "mode", "weight", "creation"],
		order_by="creation asc",
	)
	attempts = [
		adaptive.Attempt(
			row.member,
			row.item,
			bool(row.correct),
			get_datetime(row.creation),
			row.mode or "independent",
			row.weight,
		)
		for row in rows
	]
	return adaptive.replay_course(attempts, q_matrix)


def _record(
	*,
	state: adaptive.CourseState,
	graph: dict[str, Any],
	member: str,
	course: str,
	question: str,
	correct: bool,
	source: str,
	response: Any,
	condition: str | None = None,
	quiz_submission: str | None = None,
	practice_set: str | None = None,
) -> adaptive.Prediction | None:
	"""Log what Elo and BKT expected, then the outcome, as one append-only evidence row."""
	now = now_datetime()
	prediction = adaptive.observe(state, adaptive.Attempt(member, question, correct, now), graph["q_matrix"])
	frappe.get_doc(
		{
			"doctype": "CL Evidence",
			"member": member,
			"item_doctype": "LMS Question",
			"item": question,
			"course": course,
			"source": source,
			"stage": source,
			"mode": "independent",
			"correct": int(correct),
			"attempt": frappe.db.count("CL Evidence", {"member": member, "item": question}) + 1,
			"weight": elo.evidence_weight("independent"),
			"concepts": json.dumps(graph["q_matrix"].get(question) or []),
			"response": json.dumps(response, ensure_ascii=False),
			"condition": condition,
			"quiz_submission": quiz_submission,
			"practice_set": practice_set,
			"elo_p": prediction.elo_p if prediction else None,
			"bkt_p": prediction.bkt_p if prediction else None,
			"evaluator_version": "frappe_lms_quiz",
			"model_version": MODEL_VERSION,
		}
	).insert(ignore_permissions=True)
	return prediction


def on_quiz_submission(doc, method=None) -> None:
	"""doc_event: every native quiz answer becomes evidence for the course it belongs to.
	A failure here is logged, never allowed to lose the learner's quiz submission."""
	frappe.db.savepoint("cognilearn_quiz_evidence")
	try:
		_record_submission(doc)
	except Exception:
		frappe.db.rollback(save_point="cognilearn_quiz_evidence")
		frappe.log_error(
			title="CogniLearn: quiz evidence not recorded",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)


def _record_submission(doc) -> None:
	course = doc.course or frappe.db.get_value("LMS Quiz", doc.quiz, "course")
	if not course or not doc.member or doc.member == "Guest":
		return
	study = active_study(course)
	participant = _participant(study, doc.member) if study else None
	source = "recheck" if study and doc.quiz == study.recheck_quiz else "quiz"
	graph = course_graph(course)
	state = course_state(course, graph["q_matrix"])
	for row in doc.result:
		if not row.question_name or row.question_type == "Open Ended":
			continue
		_record(
			state=state,
			graph=graph,
			member=doc.member,
			course=course,
			question=row.question_name,
			correct=bool(row.is_correct),
			source=source,
			response=row.answer,
			condition=participant.condition if participant else None,
			quiz_submission=doc.name,
		)
	if participant and source == "recheck":
		frappe.db.set_value("CL Study Participant", participant.name, "status", "Complete")


# ---- study participation ---------------------------------------------------------------------


def active_study(course: str):
	name = frappe.db.get_value("CL Study", {"course": course, "active": 1}, "name", order_by="creation desc")
	return frappe.get_doc("CL Study", name) if name else None


def _participant(study, member: str):
	name = frappe.db.get_value("CL Study Participant", {"study": study.name, "member": member})
	return frappe.get_doc("CL Study Participant", name) if name else None


def ensure_participant(study, member: str):
	existing = _participant(study, member)
	if existing:
		return existing
	index = frappe.db.count("CL Study Participant", {"study": study.name})
	return frappe.get_doc(
		{
			"doctype": "CL Study Participant",
			"study": study.name,
			"member": member,
			"course": study.course,
			"enrollment_index": index,
			"condition": policy.assign_condition(index, study.study_id).value,
			"status": "Practising",
		}
	).insert(ignore_permissions=True)


def baseline_done(study, member: str) -> bool:
	if not study.baseline_quiz:
		return True
	return bool(frappe.db.exists("LMS Quiz Submission", {"quiz": study.baseline_quiz, "member": member}))


def open_set(participant):
	name = frappe.db.get_value("CL Practice Set", {"participant": participant.name, "status": "Open"})
	return frappe.get_doc("CL Practice Set", name) if name else None


def _practice_history(member: str, course: str) -> dict[str, bool]:
	history: dict[str, bool] = {}
	for row in frappe.get_all(
		"CL Evidence",
		filters={"member": member, "course": course, "item_doctype": "LMS Question"},
		fields=["item", "correct"],
		order_by="creation asc",
	):
		history[row.item] = bool(row.correct)
	return history


def plan_next_set(
	study,
	participant,
	*,
	focus_kc: str | None = None,
	regress_from: str | None = None,
	trigger: dict | None = None,
):
	"""Diagnose (agentic only), pick the next set, and log the decision before the learner sees it."""
	condition = Condition(participant.condition)
	graph = course_graph(study.course)
	state = course_state(study.course, graph["q_matrix"])
	half_life = float(repository.settings().half_life_days or elo.DEFAULT_HALF_LIFE_DAYS)
	mastery = adaptive.mastery_view(state.learner(participant.member), now_datetime(), half_life)
	diagnosis = None
	if condition == Condition.AGENTIC:
		if focus_kc:
			diagnosis = adaptive.GraphDiagnosis(focus_kc, focus_kc, [], [], "continue")
		else:
			diagnosis = adaptive.diagnose(mastery, graph["edges"], graph["order"], regress_from=regress_from)
	pool = practice_pool(study)
	history = _practice_history(participant.member, study.course)
	selection = adaptive.select_items(
		condition,
		pool=pool,
		q_matrix=graph["q_matrix"],
		history=history,
		learner=state.learner(participant.member),
		item_ratings=state.item_ratings,
		focus_kc=diagnosis.focus_kc if diagnosis else None,
		size=int(study.set_size or 4),
	)
	if not selection.questions:
		return None
	set_index = frappe.db.count("CL Practice Set", {"participant": participant.name}) + 1
	reason = _plan_reason(condition, diagnosis, graph["labels"])
	decision = _log(
		participant,
		kind="plan",
		action=f"practice_set_{set_index}",
		reason=reason,
		state=mastery,
		diagnosis=diagnosis.to_dict() if diagnosis else None,
		candidates=selection.candidates,
		chosen={
			"questions": selection.questions,
			"focus_kc": diagnosis.focus_kc if diagnosis else None,
			"trigger": trigger,
		},
	)
	return frappe.get_doc(
		{
			"doctype": "CL Practice Set",
			"participant": participant.name,
			"member": participant.member,
			"course": study.course,
			"set_index": set_index,
			"focus_kc": diagnosis.focus_kc if diagnosis else None,
			"questions": json.dumps(selection.questions),
			"status": "Open",
			"decision": decision,
		}
	).insert(ignore_permissions=True)


def _plan_reason(condition: Condition, diagnosis, labels: dict[str, str]) -> str:
	if condition == Condition.FIXED or diagnosis is None:
		return "Các câu tiếp theo theo thứ tự của khóa học."
	focus = labels.get(diagnosis.focus_kc, diagnosis.focus_kc)
	if diagnosis.reason == "gap":
		target = labels.get(diagnosis.target_kc, diagnosis.target_kc)
		return f"Bạn đang gặp khó ở “{target}”. Hệ thống cho bạn củng cố kiến thức nền “{focus}” trước."
	if diagnosis.reason == "mastered":
		return "Bạn đã vững mọi phần có dữ liệu; hệ thống cho thêm câu để củng cố."
	if diagnosis.reason == "explore":
		return f"Hệ thống chưa có dữ liệu về “{focus}”, nên bạn thử vài câu để kiểm tra."
	return f"Lượt này tập trung vào “{focus}”, phần bạn còn yếu nhất."


def _log(participant, *, kind: str, action: str, reason: str, **payload) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "CL Decision Log",
			"member": participant.member,
			"course": participant.course,
			"participant": participant.name,
			"kind": kind,
			"action": action,
			"condition": participant.condition,
			"policy_version": adaptive.ADAPTIVE_VERSION,
			"model_version": MODEL_VERSION,
			"propensity": 1.0,
			"reason": reason,
			**{
				key: json.dumps(value, ensure_ascii=False, default=str)
				for key, value in payload.items()
				if value is not None
			},
		}
	).insert(ignore_permissions=True)
	return doc.name


# ---- answering -------------------------------------------------------------------------------


def grade(question: str, answer: Any) -> tuple[bool, list[str], list[str]]:
	"""Grade with the LMS's own quiz rules. Practice questions are never on the recheck, so the
	learner also gets the explanation of their choice and the right answer to learn from."""
	doc = frappe.db.get_value(
		"LMS Question",
		question,
		["type", *QUESTION_OPTION_FIELDS, *QUESTION_CORRECTNESS_FIELDS, *QUESTION_EXPLANATION_FIELDS],
		as_dict=True,
	)
	if doc.type == "User Input":
		text = answer[0] if isinstance(answer, list) and answer else answer
		return bool(check_input_answers(question, str(text or ""))), [], []
	answers = answer if isinstance(answer, list) else [answer]
	fields = list(
		zip(QUESTION_OPTION_FIELDS, QUESTION_CORRECTNESS_FIELDS, QUESTION_EXPLANATION_FIELDS, strict=True)
	)
	right = [doc[option] for option, correct, _ in fields if doc[option] and doc[correct]]
	explanations = [
		doc[explanation] for option, _, explanation in fields if doc[option] in answers and doc[explanation]
	]
	correct = bool(verify_answer(question, answers))
	if not correct:
		explanations += [
			doc[explanation]
			for option, is_right, explanation in fields
			if doc[option] and doc[is_right] and doc[explanation]
		]
	return correct, explanations, right


def answer_practice(study, participant, practice_set, question: str, answer: Any) -> dict[str, Any]:
	questions = _json(practice_set.questions) or []
	if question not in questions:
		frappe.throw("This question is not in your current practice set.", frappe.PermissionError)
	if frappe.db.exists("CL Evidence", {"practice_set": practice_set.name, "item": question}):
		frappe.throw("You already answered this question.")
	correct, explanations, right = grade(question, answer)
	graph = course_graph(study.course)
	state = course_state(study.course, graph["q_matrix"])
	_record(
		state=state,
		graph=graph,
		member=participant.member,
		course=study.course,
		question=question,
		correct=correct,
		source="practice",
		response=answer,
		condition=participant.condition,
		practice_set=practice_set.name,
	)
	reply: dict[str, Any] = {"correct": correct, "explanations": explanations, "correct_answers": right}
	results = frappe.get_all("CL Evidence", filters={"practice_set": practice_set.name}, pluck="correct")
	if len(results) >= len(questions):
		reply["replan"] = _close_set(study, participant, practice_set, [bool(r) for r in results], graph)
	return reply


def _close_set(study, participant, practice_set, results: list[bool], graph) -> dict[str, Any]:
	condition = Condition(participant.condition)
	sets_done = frappe.db.count("CL Practice Set", {"participant": participant.name, "status": "Done"}) + 1
	pool_left = len(
		[q for q in practice_pool(study) if q not in _practice_history(participant.member, study.course)]
	)
	decision = adaptive.replan(
		condition,
		set_results=results,
		sets_done=sets_done,
		budget_sets=int(study.budget_sets or 3),
		pool_left=pool_left,
		focus_label=graph["labels"].get(practice_set.focus_kc),
	)
	frappe.db.set_value(
		"CL Practice Set", practice_set.name, {"status": "Done", "accuracy": decision.set_accuracy}
	)
	_log(
		participant,
		kind="replan",
		action=decision.action,
		reason=decision.reason_for_student,
		chosen={
			"practice_set": practice_set.name,
			"set_accuracy": decision.set_accuracy,
			"focus_kc": practice_set.focus_kc,
		},
	)
	trigger = {"replan": decision.action, "after_set": practice_set.name}
	if decision.action == "schedule_recheck":
		due = add_to_date(now_datetime(), hours=int(study.recheck_delay_hours or 72))
		frappe.db.set_value(
			"CL Study Participant", participant.name, {"status": "Recheck Scheduled", "recheck_due_at": due}
		)
		_log(
			participant,
			kind="recheck",
			action="scheduled",
			reason=decision.reason_for_student,
			chosen={"due_at": str(due), "quiz": study.recheck_quiz},
		)
	elif decision.action == "continue" and condition == Condition.AGENTIC:
		plan_next_set(study, participant, focus_kc=practice_set.focus_kc, trigger=trigger)
	elif decision.action == "regress":
		plan_next_set(study, participant, regress_from=practice_set.focus_kc, trigger=trigger)
	else:
		plan_next_set(study, participant, trigger=trigger)
	return decision.to_dict()


# ---- recheck scheduler -----------------------------------------------------------------------


def remind_due_rechecks() -> None:
	"""Hourly: open the recheck for learners whose delay has passed and notify them once."""
	for row in frappe.get_all(
		"CL Study Participant",
		filters={"status": "Recheck Scheduled", "recheck_due_at": ["<=", now_datetime()]},
		fields=["name", "member", "study"],
	):
		quiz = frappe.db.get_value("CL Study", row.study, "recheck_quiz")
		frappe.db.set_value(
			"CL Study Participant", row.name, {"status": "Recheck Due", "recheck_notified": 1}
		)
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": row.member,
				"type": "Alert",
				"subject": "Đã đến lúc làm bài kiểm tra lại",
				"email_content": "Bài kiểm tra lại giúp đo xem kiến thức bạn luyện tập có còn giữ được sau vài ngày không.",
				"link": f"/lms/quiz/{quiz}" if quiz else None,
			}
		).insert(ignore_permissions=True)


def recheck_open(participant) -> bool:
	if participant.status == "Recheck Due":
		return True
	due = participant.recheck_due_at
	return (
		participant.status == "Recheck Scheduled" and due is not None and get_datetime(due) <= now_datetime()
	)


# ---- Jev leak gate ---------------------------------------------------------------------------


def run_leak_gate(study) -> dict[str, Any]:
	"""Keep practice questions that would give away a recheck question out of the pool."""
	graph = course_graph(study.course)
	recheck_ids = quiz_questions(study.recheck_quiz)
	held_out = set(recheck_ids) | set(quiz_questions(study.baseline_quiz))
	practice_ids = [q for q in course_questions(study.course) if q not in held_out]
	checks = adaptive.find_leaks(
		repository.get_judge(), _texts(practice_ids), _texts(recheck_ids), graph["q_matrix"]
	)
	excluded = sorted({check["practice"] for check in checks if check["leak"]})
	study.db_set({"excluded_questions": json.dumps(excluded), "leak_checks": json.dumps(checks)})
	return {"checked_pairs": len(checks), "excluded": excluded}


def _texts(questions: list[str]) -> list[dict[str, str]]:
	rows = []
	for name in questions:
		question = repository._question(name)
		if question:
			options = "; ".join(question["options"])
			rows.append(
				{
					"id": name,
					"text": f"{question['text']} {('Lựa chọn: ' + options) if options else ''}".strip(),
				}
			)
	return rows


# ---- student view ----------------------------------------------------------------------------


def public_question(name: str) -> dict[str, Any]:
	doc = frappe.db.get_value(
		"LMS Question", name, ["name", "question", "type", "multiple", *QUESTION_OPTION_FIELDS], as_dict=True
	)
	return {
		"name": doc.name,
		"question": doc.question,
		"type": doc.type,
		"multiple": bool(doc.multiple),
		"options": [doc[field] for field in QUESTION_OPTION_FIELDS if doc[field]],
	}


def student_view(study, member: str) -> dict[str, Any]:
	"""What the learner sees. The study condition is never sent (blinding)."""
	view: dict[str, Any] = {
		"study": True,
		"baseline_quiz": study.baseline_quiz,
		"recheck_quiz": study.recheck_quiz,
	}
	if not baseline_done(study, member):
		return {**view, "step": "baseline"}
	participant = _participant(study, member)
	if not participant:
		return {**view, "step": "start"}
	if participant.status == "Complete":
		return {**view, "step": "complete"}
	if participant.status in ("Recheck Scheduled", "Recheck Due"):
		return {
			**view,
			"step": "recheck" if recheck_open(participant) else "waiting",
			"recheck_due_at": participant.recheck_due_at,
		}
	practice_set = open_set(participant)
	if not practice_set:
		return {**view, "step": "start"}
	questions = _json(practice_set.questions) or []
	answered = {
		row.item: bool(row.correct)
		for row in frappe.get_all(
			"CL Evidence", filters={"practice_set": practice_set.name}, fields=["item", "correct"]
		)
	}
	reason = (
		frappe.db.get_value("CL Decision Log", practice_set.decision, "reason")
		if practice_set.decision
		else None
	)
	last_replan = frappe.get_all(
		"CL Decision Log",
		filters={"participant": participant.name, "kind": "replan"},
		fields=["action", "reason"],
		order_by="creation desc",
		limit=1,
	)
	return {
		**view,
		"step": "practice",
		"set_index": practice_set.set_index,
		"budget_sets": int(study.budget_sets or 3),
		"reason": reason,
		"last_replan": last_replan[0] if last_replan else None,
		"questions": [public_question(q) for q in questions],
		"answered": answered,
	}


def _json(value):
	if value in (None, ""):
		return None
	return json.loads(value) if isinstance(value, str) else value
