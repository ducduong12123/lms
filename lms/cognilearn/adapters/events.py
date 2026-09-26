"""Course content changes -> background knowledge-mapping job (PT0)."""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime

from lms.cognilearn.adapters import repository
from lms.cognilearn.core.knowledge_map import MAPPER_VERSION, build_knowledge_map


def _course_of(doc) -> str | None:
	if doc.doctype == "LMS Course":
		return doc.name
	return getattr(doc, "course", None)


def on_content_change(doc, method=None):
	"""doc_events hook for LMS Course / Course Chapter / Course Lesson / LMS Quiz."""
	course = _course_of(doc)
	if not course or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import:
		return
	if not frappe.db.get_single_value("CL Settings", "auto_map_on_change"):
		return
	if not frappe.db.get_single_value("CL Settings", "llm_base_url"):
		return
	enqueue_mapping(course)


def enqueue_mapping(course: str, force: bool = False) -> None:
	frappe.enqueue(
		"lms.cognilearn.adapters.events.map_course",
		queue="long",
		timeout=1800,
		job_id=f"cognilearn-map-{course}",
		deduplicate=True,
		enqueue_after_commit=True,
		course=course,
		force=force,
	)


def _last_content_hash(course: str) -> str | None:
	summary = frappe.db.get_value(
		"CL Knowledge Map Run", {"course": course, "status": "Done"}, "summary", order_by="creation desc"
	)
	return (json.loads(summary) if summary else {}).get("content_hash")


def map_course(course: str, force: bool = False) -> str | None:
	snapshot = repository.course_snapshot(course)
	content_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
	if not force and content_hash == _last_content_hash(course):
		return None  # saves that do not change lessons or questions do not re-run the LLM
	run = frappe.get_doc(
		{"doctype": "CL Knowledge Map Run", "course": course, "status": "Running", "mapper_version": MAPPER_VERSION}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	try:
		config = repository.settings()
		judge = repository.get_judge()
		llm = repository.get_llm()
		result = build_knowledge_map(
			snapshot,
			llm=llm,
			judge=judge,
			accept_at=float(config.accept_threshold or 0.8),
			reject_at=float(config.reject_threshold or 0.2),
		)
		repository.save_knowledge_map(course, result, snapshot)
		summary = result.summary()
		run.update(
			{
				"status": "Done",
				"judge_source": result.judge_source,
				"llm_model": llm.model,
				"automatic_share": summary["automatic_share"] * 100,
				"summary": json.dumps({**summary, "content_hash": content_hash, "finished_at": str(now_datetime())}),
				"result": json.dumps(result.to_dict(), ensure_ascii=False),
			}
		)
	except Exception as error:
		frappe.db.rollback()
		run.reload()
		run.update({"status": "Failed", "error": f"{type(error).__name__}: {error}"[:1000]})
		frappe.log_error(title="CogniLearn knowledge map failed", message=frappe.get_traceback())
	run.save(ignore_permissions=True)
	frappe.db.commit()
	return run.name
