"""Elo vs BKT on next-response prediction, from an evidence export (no Frappe needed).

Two views of the same question:
  * logged   - the P(correct) each model wrote into CL Evidence *before* the outcome was seen
               (prospective; what the pilot pre-registers);
  * replayed - both models re-run over the evidence with the current, teacher-reviewed Q-matrix.

    python -m lms.cognilearn.research.model_comparison evidence.csv [--sources practice,recheck]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime

from lms.cognilearn.core import adaptive


def auc(pairs: list[tuple[float, int]]) -> float | None:
	positives = [p for p, y in pairs if y]
	negatives = [p for p, y in pairs if not y]
	if not positives or not negatives:
		return None
	wins = sum((p > q) + 0.5 * (p == q) for p in positives for q in negatives)
	return round(wins / (len(positives) * len(negatives)), 4)


def rmse(pairs: list[tuple[float, int]]) -> float | None:
	return round(math.sqrt(sum((p - y) ** 2 for p, y in pairs) / len(pairs)), 4) if pairs else None


def log_loss(pairs: list[tuple[float, int]]) -> float | None:
	if not pairs:
		return None
	eps = 1e-6
	return round(
		-sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in pairs) / len(pairs),
		4,
	)


def score(pairs: list[tuple[float, int]]) -> dict:
	return {"n": len(pairs), "auc": auc(pairs), "rmse": rmse(pairs), "log_loss": log_loss(pairs)}


def compare(rows: list[dict], sources: set[str] | None = None) -> dict:
	chosen = [
		r for r in rows if (not sources or r["source"] in sources) and json.loads(r["concepts"] or "[]")
	]
	logged = [r for r in chosen if r["elo_p"] not in ("", None) and r["bkt_p"] not in ("", None)]
	result = {
		"logged": {
			"elo": score([(float(r["elo_p"]), int(r["correct"])) for r in logged]),
			"bkt": score([(float(r["bkt_p"]), int(r["correct"])) for r in logged]),
		}
	}
	# Replay over every row (the models learn from all sources), score only the chosen ones.
	q_matrix = {r["item"]: json.loads(r["concepts"] or "[]") for r in rows}
	attempts = [
		adaptive.Attempt(
			r["member"],
			r["item"],
			bool(int(r["correct"])),
			datetime.fromisoformat(r["at"]),
			r.get("mode") or "independent",
		)
		for r in rows
	]
	state = adaptive.replay_course(attempts, q_matrix)
	keep = {(r["member"], r["item"], r["at"]) for r in chosen}
	ordered = sorted(rows, key=lambda r: r["at"])
	predictions = [p for p in state.predictions]
	scored_rows = [r for r in ordered if json.loads(r["concepts"] or "[]")]
	elo_pairs, bkt_pairs = [], []
	for row, prediction in zip(scored_rows, predictions, strict=True):
		if (row["member"], row["item"], row["at"]) in keep:
			elo_pairs.append((prediction.elo_p, int(prediction.correct)))
			bkt_pairs.append((prediction.bkt_p, int(prediction.correct)))
	result["replayed"] = {"elo": score(elo_pairs), "bkt": score(bkt_pairs)}
	return result


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("csv")
	parser.add_argument("--sources", default="", help="comma-separated: quiz,practice,recheck (default: all)")
	args = parser.parse_args()
	with open(args.csv, encoding="utf-8") as handle:
		rows = list(csv.DictReader(handle))
	sources = {s for s in args.sources.split(",") if s} or None
	print(json.dumps(compare(rows, sources), indent=1))


if __name__ == "__main__":
	main()
