"""Research export for a CogniLearn study: pseudonymised CSVs, one folder per export.

    bench --site <site> execute lms.cognilearn.research.export.export_study --kwargs '{"course": "<course>"}'

Learner emails never leave the site: each becomes sha256(study_id + email)[:12].
"""

from __future__ import annotations

import csv
import hashlib
import json
import os

import frappe
from frappe.utils import get_datetime, now_datetime

from lms.cognilearn.adapters import study as study_adapter


def _pseudonym(study_id: str, member: str) -> str:
	return hashlib.sha256(f"{study_id}:{member}".encode()).hexdigest()[:12]


def _write(folder: str, name: str, rows: list[dict]) -> int:
	path = os.path.join(folder, name)
	with open(path, "w", encoding="utf-8", newline="") as handle:
		if rows:
			writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
			writer.writeheader()
			writer.writerows(rows)
	return len(rows)


def export_study(course: str, folder: str | None = None) -> dict:
	frappe.only_for("System Manager")
	found = study_adapter.active_study(course) or frappe.get_last_doc("CL Study", filters={"course": course})
	study_id = found.study_id
	folder = folder or frappe.get_site_path(
		"private", "files", f"cognilearn_{study_id}_{now_datetime():%Y%m%d%H%M%S}"
	)
	os.makedirs(folder, exist_ok=True)
	anon = lambda member: _pseudonym(study_id, member)  # noqa: E731
	graph = study_adapter.course_graph(course)
	labels = graph["labels"]

	participants = frappe.get_all(
		"CL Study Participant",
		filters={"study": found.name},
		fields=["member", "condition", "enrollment_index", "status", "recheck_due_at"],
		order_by="enrollment_index asc",
	)
	condition_of = {p.member: p.condition for p in participants}
	counts = {
		"participants": _write(
			folder,
			"participants.csv",
			[
				{
					"learner": anon(p.member),
					"condition": p.condition,
					"enrollment_index": p.enrollment_index,
					"status": p.status,
					"recheck_due_at": p.recheck_due_at,
				}
				for p in participants
			],
		)
	}
	evidence = frappe.get_all(
		"CL Evidence",
		filters={"course": course, "item_doctype": "LMS Question"},
		fields=[
			"member",
			"item",
			"source",
			"correct",
			"mode",
			"concepts",
			"elo_p",
			"bkt_p",
			"practice_set",
			"quiz_submission",
			"creation",
			"model_version",
		],
		order_by="creation asc",
	)
	counts["evidence"] = _write(
		folder,
		"evidence.csv",
		[
			{
				"member": anon(row.member),
				"condition": condition_of.get(row.member, ""),
				"item": row.item,
				"source": row.source,
				"correct": int(row.correct),
				"mode": row.mode,
				# The Q-matrix row as it is now (teacher reviewed), for replay; plus what was logged.
				"concepts": json.dumps(graph["q_matrix"].get(row.item, [])),
				"concepts_at_time": row.concepts or "[]",
				"elo_p": "" if not json.loads(row.concepts or "[]") else row.elo_p,
				"bkt_p": "" if not json.loads(row.concepts or "[]") else row.bkt_p,
				"practice_set": row.practice_set or "",
				"at": get_datetime(row.creation).isoformat(),
				"model_version": row.model_version,
			}
			for row in evidence
		],
	)
	decisions = frappe.get_all(
		"CL Decision Log",
		filters={"course": course},
		fields=[
			"member",
			"kind",
			"action",
			"condition",
			"policy_version",
			"model_version",
			"propensity",
			"reason",
			"state",
			"diagnosis",
			"candidates",
			"chosen",
			"creation",
		],
		order_by="creation asc",
	)
	counts["decisions"] = _write(
		folder,
		"decisions.csv",
		[
			{
				**{k: v for k, v in d.items() if k not in ("member", "creation")},
				"learner": anon(d.member),
				"at": get_datetime(d.creation).isoformat(),
			}
			for d in decisions
		],
	)
	counts["q_matrix"] = _write(
		folder,
		"q_matrix.csv",
		[
			{
				"question": r.question,
				"concept": labels.get(r.knowledge_component, r.knowledge_component),
				"status": r.status,
				"probability": r.probability,
				"judged_by": r.source,
			}
			for r in frappe.get_all(
				"CL Item Map",
				filters={"course": course},
				fields=["question", "knowledge_component", "status", "probability", "source"],
			)
		],
	)
	counts["edges"] = _write(
		folder,
		"edges.csv",
		[
			{
				"prerequisite": labels.get(r.prerequisite, r.prerequisite),
				"dependent": labels.get(r.dependent, r.dependent),
				"status": r.status,
				"probability": r.probability,
				"judged_by": r.source,
				"origin": r.origin,
			}
			for r in frappe.get_all(
				"CL Knowledge Edge",
				filters={"course": course},
				fields=["prerequisite", "dependent", "status", "probability", "source", "origin"],
			)
		],
	)
	with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as handle:
		handle.write(
			f"CogniLearn study {study_id} on course {course}, exported {now_datetime()}.\n"
			"Learners are pseudonymised (sha256 of study id + email, 12 hex).\n"
			"evidence.csv: one row per answer; elo_p/bkt_p = each model's P(correct) logged before the outcome.\n"
			"Compare the models: python -m lms.cognilearn.research.model_comparison evidence.csv --sources practice,recheck\n"
		)
	return {"folder": folder, **counts}
