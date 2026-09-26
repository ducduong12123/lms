"""PT0 reliability: how well does the automatic Q-matrix step agree with a published expert Q-matrix?

Benchmark: Tatsuoka's fraction subtraction test (20 items, 8 attributes). Items as listed in
Table 12 of arXiv:1303.0426 (from K. K. Tatsuoka, 1990); expert Q-matrix of de la Torre &
Douglas (2004) as shipped in the R package CDM (``fraction.subtraction.qmatrix``).

The attribute catalogue is given (as a teacher would name the skills); the mapper judges every
item x attribute cell exactly as it does for a course. Needs no Frappe site:

    TYPESAFE_API_KEY=... python -m lms.cognilearn.research.tatsuoka_benchmark [--lang en|vi] [--out file.json]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from lms.cognilearn.core.judge import FallbackJudge, JevJudge
from lms.cognilearn.core.knowledge_map import ACCEPT_AT, REJECT_AT, build_knowledge_map

ITEMS = [
	"5/3 − 3/4", "3/4 − 3/8", "5/6 − 1/9", "3 1/2 − 2 3/2", "4 3/5 − 3 4/10",
	"6/7 − 4/7", "3 − 2 1/5", "2/3 − 2/3", "3 7/8 − 2", "4 4/12 − 2 7/12",
	"4 1/3 − 2 4/3", "11/8 − 1/8", "3 3/8 − 2 5/6", "3 4/5 − 3 2/5", "2 − 1/3",
	"4 5/7 − 1 4/7", "7 3/5 − 4/5", "4 1/10 − 2 8/10", "4 − 1 4/3", "4 1/3 − 1 5/3",
]  # fmt: skip

ATTRIBUTES = {
	"en": [
		("a1", "Convert a whole number to a fraction", "e.g. write 3 as 3/1 or as 12/4 before subtracting"),
		(
			"a2",
			"Separate a whole number from a fraction",
			"treat a mixed number as its whole part and its fraction part",
		),
		(
			"a3",
			"Simplify before subtracting",
			"rewrite an improper fraction part (e.g. 2 3/2 as 3 1/2) before subtracting",
		),
		(
			"a4",
			"Find a common denominator",
			"rewrite fractions with different denominators over the same denominator",
		),
		(
			"a5",
			"Borrow from the whole number part",
			"take 1 from the whole part when the first fraction part is smaller",
		),
		(
			"a6",
			"Column borrow to subtract the second numerator from the first",
			"borrow within the numerators so the larger is subtracted from the smaller",
		),
		("a7", "Subtract numerators", "subtract the numerators once the fractions share a denominator"),
		("a8", "Reduce answers to simplest form", "reduce the resulting fraction to lowest terms"),
	],
	"vi": [
		("a1", "Đổi số nguyên thành phân số", "ví dụ viết 3 thành 3/1 hoặc 12/4 trước khi trừ"),
		("a2", "Tách phần nguyên khỏi phân số", "xử lý hỗn số thành phần nguyên và phần phân số riêng"),
		(
			"a3",
			"Rút gọn trước khi trừ",
			"viết lại phần phân số lớn hơn 1 (ví dụ 2 3/2 thành 3 1/2) trước khi trừ",
		),
		("a4", "Quy đồng mẫu số", "đưa các phân số khác mẫu về cùng một mẫu"),
		("a5", "Mượn từ phần nguyên", "lấy 1 từ phần nguyên khi phần phân số của số bị trừ nhỏ hơn"),
		("a6", "Mượn theo cột để trừ tử số", "mượn trong tử số để lấy tử lớn trừ tử nhỏ"),
		("a7", "Trừ các tử số", "trừ tử số khi hai phân số đã cùng mẫu"),
		("a8", "Rút gọn kết quả về tối giản", "rút gọn phân số kết quả về dạng tối giản"),
	],
}

# de la Torre & Douglas (2004), CDM::fraction.subtraction.qmatrix; rows = items 1..20, cols = a1..a8.
EXPERT = [
	"00010110", "00010010", "00010010", "01101010", "01010011",
	"00000010", "11000010", "00000010", "01000000", "01001011",
	"01001010", "00000011", "01011010", "01000010", "10000010",
	"01000010", "01001010", "01001110", "11101010", "01101010",
]  # fmt: skip

# The original test shows only the expression. An earlier version of this benchmark added
# "write the answer in simplest form", which made every item look like it needed a8.
PROMPT = {
	"en": "Compute: {item}",
	"vi": "Tính: {item}",
}


def course(lang: str) -> dict[str, Any]:
	return {
		"name": f"tatsuoka-{lang}",
		"title": "Fraction subtraction" if lang == "en" else "Trừ phân số",
		"lessons": [
			{
				"id": "fractions",
				"title": "Fraction subtraction",
				"text": "",
				"questions": [
					{"id": f"item{i + 1}", "text": PROMPT[lang].format(item=item), "options": []}
					for i, item in enumerate(ITEMS)
				],
			}
		],
	}


def catalogue(lang: str) -> list[dict[str, Any]]:
	return [
		{
			"key": key,
			"label": label,
			"description": description,
			"prerequisites": [],
			"lessons": ["fractions"],
			"questions": [],
		}
		for key, label, description in ATTRIBUTES[lang]
	]


# ---- agreement statistics --------------------------------------------------------------------


def kappa(pairs: list[tuple[int, int]]) -> float | None:
	"""Cohen's kappa for two binary raters."""
	n = len(pairs)
	if not n:
		return None
	observed = sum(1 for a, b in pairs if a == b) / n
	p_a = sum(a for a, _ in pairs) / n
	p_b = sum(b for _, b in pairs) / n
	expected = p_a * p_b + (1 - p_a) * (1 - p_b)
	return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def auc(scored: list[tuple[float, int]]) -> float | None:
	"""Probability that a random expert-1 cell gets a higher p than a random expert-0 cell."""
	positives = [p for p, y in scored if y == 1]
	negatives = [p for p, y in scored if y == 0]
	if not positives or not negatives:
		return None
	wins = sum((p > q) + 0.5 * (p == q) for p in positives for q in negatives)
	return round(wins / (len(positives) * len(negatives)), 3)


def evaluate(cells: list[dict[str, Any]], accept_at: float, reject_at: float) -> dict[str, Any]:
	judged = [c for c in cells if c["p"] is not None]
	at_half = [(int(c["p"] >= 0.5), c["expert"]) for c in judged]
	auto = [c for c in judged if c["p"] >= accept_at or c["p"] <= reject_at]
	auto_pairs = [(int(c["p"] >= accept_at), c["expert"]) for c in auto]
	tp = sum(1 for m, e in at_half if m and e)
	fp = sum(1 for m, e in at_half if m and not e)
	fn = sum(1 for m, e in at_half if not m and e)
	per_attribute = {}
	for key in sorted({c["attribute"] for c in judged}):
		rows = [(int(c["p"] >= 0.5), c["expert"]) for c in judged if c["attribute"] == key]
		per_attribute[key] = {
			"kappa": kappa(rows),
			"expert_ones": sum(e for _, e in rows),
			"model_ones": sum(m for m, _ in rows),
		}
	return {
		"cells": len(cells),
		"judged": len(judged),
		"auc": auc([(c["p"], c["expert"]) for c in judged]),
		"at_0.5": {
			"accuracy": round(sum(1 for m, e in at_half if m == e) / len(at_half), 3) if at_half else None,
			"kappa": kappa(at_half),
			"precision": round(tp / (tp + fp), 3) if tp + fp else None,
			"recall": round(tp / (tp + fn), 3) if tp + fn else None,
		},
		"routed": {
			"thresholds": [accept_at, reject_at],
			"automatic_share": round(len(auto) / len(judged), 3) if judged else None,
			"automatic_accuracy": round(sum(1 for m, e in auto_pairs if m == e) / len(auto_pairs), 3)
			if auto_pairs
			else None,
			"automatic_kappa": kappa(auto_pairs),
			"review_cells": len(judged) - len(auto),
			"review_expert_ones": sum(c["expert"] for c in judged if reject_at < c["p"] < accept_at),
		},
		"per_attribute": per_attribute,
	}


def run(lang: str, judge) -> dict[str, Any]:
	started = time.monotonic()
	result = build_knowledge_map(course(lang), llm=None, judge=judge, catalogue=catalogue(lang))
	elapsed = round(time.monotonic() - started, 1)
	keys = [key for key, _, _ in ATTRIBUTES[lang]]
	p = {(link["question"], link["kc"]): link["p"] for link in result.q_matrix}
	cells = [
		{
			"item": i + 1,
			"attribute": key,
			"expert": int(EXPERT[i][k]),
			"p": p.get((f"item{i + 1}", key)),
		}
		for i in range(len(ITEMS))
		for k, key in enumerate(keys)
	]
	return {
		"lang": lang,
		"judge": result.judge_source,
		"seconds": elapsed,
		"metrics": evaluate(cells, ACCEPT_AT, REJECT_AT),
		"cells": cells,
	}


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--lang", choices=["en", "vi", "both"], default="both")
	parser.add_argument("--out", default=None)
	args = parser.parse_args()
	key = os.environ.get("TYPESAFE_API_KEY", "")
	judge = JevJudge(key) if key else FallbackJudge()
	reports = [run(lang, judge) for lang in (["en", "vi"] if args.lang == "both" else [args.lang])]
	for report in reports:
		print(json.dumps({k: v for k, v in report.items() if k != "cells"}, ensure_ascii=False, indent=1))
	if args.out:
		with open(args.out, "w", encoding="utf-8") as handle:
			json.dump(reports, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
	main()
