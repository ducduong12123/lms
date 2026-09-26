"""Frozen content for the singly-linked-list insertion pilot (ported from CogniLearn cycle 2).

Items are plain dicts so the Frappe adapter can store them in ``CL Item`` unchanged.
"""

from __future__ import annotations

from typing import Any

STUDY_ID = "ctdlgt_sll_insertion_pilot_v1"
TARGET_CONCEPT = "sll_insertion_after_k"
CONTENT_VERSION = "ctdlgt_sll_insertion_content_v1"

# Knowledge components and prerequisite edges (prerequisite -> dependent).
KNOWLEDGE_COMPONENTS = {
	"node_structure": "Cấu trúc node (data, next)",
	"head_pointer": "Con trỏ head",
	"sll_next_pointer": "Liên kết next và successor",
	"traversal_counting": "Duyệt và đếm vị trí",
	"kth_node_access": "Truy cập node ở vị trí k",
	"edge_cases": "Trường hợp biên (đầu, cuối, rỗng)",
	"sll_insertion_after_k": "Chèn node sau vị trí k",
}
PREREQUISITES = [
	("node_structure", "sll_next_pointer"),
	("node_structure", "head_pointer"),
	("head_pointer", "traversal_counting"),
	("traversal_counting", "kth_node_access"),
	("sll_next_pointer", "sll_insertion_after_k"),
	("kth_node_access", "sll_insertion_after_k"),
	("sll_insertion_after_k", "edge_cases"),
]


def _item(
	code: str,
	stage: str,
	item_type: str,
	stem: str,
	*,
	difficulty: str,
	correct: str,
	concepts: list[str],
	prerequisites: list[str],
	options: list[tuple[str, str]] | None = None,
	answer_mode: str = "option",
	accepted_answers: list[str] | None = None,
	expected_tokens: list[str] | None = None,
	misconception_codes: list[str] | None = None,
	misconception_by_answer: dict[str, str] | None = None,
	hint_ladder: list[str] | None = None,
) -> dict[str, Any]:
	return {
		"code": code,
		"study_id": STUDY_ID,
		"content_version": CONTENT_VERSION,
		"stage": stage,
		"item_type": item_type,
		"stem": stem,
		"difficulty": difficulty,
		"options": [{"key": key, "text": text} for key, text in options or []],
		"correct_answer": correct,
		"answer_mode": answer_mode,
		"accepted_answers": list(accepted_answers or []),
		"expected_tokens": list(expected_tokens or []),
		"concepts": list(concepts),
		"prerequisites": list(prerequisites),
		"misconception_codes": list(misconception_codes or []),
		"misconception_by_answer": dict(misconception_by_answer or {}),
		"hint_ladder": list(hint_ladder or []),
	}


ITEMS: list[dict[str, Any]] = [
	_item(
		"SLL-PILOT-B-01", "baseline", "mcq",
		"Khi chèn node mới sau node ở vị trí k, liên kết nào cần được giữ lại trước khi nối node mới?",
		difficulty="easy",
		options=[("A", "new_node->next"), ("B", "node_k->next"), ("C", "head->next"), ("D", "nullptr")],
		correct="B", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "head_pointer"], misconception_codes=["lost_successor"],
		misconception_by_answer={"A": "lost_successor", "C": "head_confusion", "D": "lost_successor"},
		hint_ladder=[
			"Hãy xác định node nào đang đứng sau node k.",
			"Nếu không lưu node sau k, phần còn lại của danh sách sẽ ra sao?",
		],
	),
	_item(
		"SLL-PILOT-B-02", "baseline", "mcq",
		"Thứ tự câu lệnh nào bảo toàn danh sách khi chèn new_node sau node_k?",
		difficulty="medium",
		options=[
			("A", "node_k->next = new_node; new_node->next = node_k->next"),
			("B", "new_node->next = node_k->next; node_k->next = new_node"),
			("C", "head = new_node; new_node->next = node_k"),
			("D", "node_k = new_node; new_node->next = nullptr"),
		],
		correct="B", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "kth_node_access", "sll_next_pointer"],
		misconception_codes=["overwrite_before_linking", "wrong_statement_order"],
		misconception_by_answer={"A": "overwrite_before_linking", "C": "head_confusion", "D": "wrong_statement_order"},
		hint_ladder=["Một câu lệnh phải nối new_node với successor cũ trước.", "Hãy đọc hai câu lệnh theo thứ tự thời gian."],
	),
	_item(
		"SLL-PILOT-B-03", "baseline", "mcq",
		"Với danh sách head -> 3 -> 5 -> 7, chèn 4 sau vị trí k = 0 sẽ tạo ra thứ tự nào?",
		difficulty="easy",
		options=[
			("A", "head -> 4 -> 3 -> 5 -> 7"), ("B", "head -> 3 -> 4 -> 5 -> 7"),
			("C", "head -> 3 -> 5 -> 4 -> 7"), ("D", "head -> 3 -> 5 -> 7 -> 4"),
		],
		correct="B", concepts=["sll_insertion_after_k", "kth_node_access"],
		prerequisites=["node_structure", "head_pointer", "traversal_counting"],
		misconception_codes=["wrong_k_boundary", "off_by_one"],
		misconception_by_answer={"A": "wrong_k_boundary", "C": "off_by_one", "D": "off_by_one"},
		hint_ladder=["k = 0 là node đầu tiên, không phải vị trí trước head.", "Hãy viết lại successor của node 3 sau phép chèn."],
	),
	_item(
		"SLL-PILOT-B-04", "baseline", "mcq",
		"Nếu chèn node mới sau node cuối của danh sách, giá trị đúng của new_node->next là gì?",
		difficulty="medium",
		options=[("A", "head"), ("B", "node_k"), ("C", "nullptr"), ("D", "new_node")],
		correct="C", concepts=["sll_insertion_after_k", "edge_cases"],
		prerequisites=["node_structure", "sll_next_pointer"], misconception_codes=["tail_boundary_confusion"],
		misconception_by_answer={"A": "head_confusion", "B": "tail_boundary_confusion", "D": "cycle_creation"},
		hint_ladder=["Node cuối hiện tại không có successor.", "Sau khi chèn sau tail, node mới sẽ trở thành tail."],
	),
	_item(
		"SLL-PILOT-G-01", "guided_practice", "tracing",
		"Sau khi chèn 4 sau node 3 trong head -> 3 -> 5 -> 7, hãy viết chuỗi node từ head đến cuối.",
		difficulty="easy", correct="head -> 3 -> 4 -> 5 -> 7",
		concepts=["sll_insertion_after_k", "sll_next_pointer"], prerequisites=["node_structure", "head_pointer"],
		answer_mode="normalized_text",
		accepted_answers=["head->3->4->5->7", "head -> 3 -> 4 -> 5 -> 7", "3 -> 4 -> 5 -> 7"],
		misconception_codes=["lost_successor", "wrong_k_boundary"],
		hint_ladder=["Node mới đứng ngay sau node 3.", "Successor cũ của node 3 là node 5; đừng bỏ nó."],
	),
	_item(
		"SLL-PILOT-G-02", "guided_practice", "pointer_order",
		"Sửa thứ tự hai câu lệnh để chèn new_node sau node_k mà không làm mất successor cũ.",
		difficulty="medium", correct="new_node->next = node_k->next; node_k->next = new_node",
		concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "kth_node_access", "sll_next_pointer"],
		options=[("A", "node_k->next = new_node"), ("B", "new_node->next = node_k->next")],
		answer_mode="ordered_tokens", expected_tokens=["new_node->next", "node_k->next"],
		accepted_answers=["new_node->next = node_k->next; node_k->next = new_node"],
		misconception_codes=["overwrite_before_linking", "wrong_statement_order"],
		hint_ladder=["Câu lệnh đầu tiên cần dùng successor cũ của node_k.", "Sau đó mới cho node_k trỏ tới new_node."],
	),
	_item(
		"SLL-PILOT-G-03", "guided_practice", "mcq",
		"Điều gì xảy ra nếu thực hiện node_k->next = new_node trước khi gán new_node->next?",
		difficulty="medium",
		options=[
			("A", "Danh sách luôn tự động giữ successor cũ"),
			("B", "Có thể mất successor cũ nếu chưa lưu liên kết"),
			("C", "head tự động đổi thành new_node"),
			("D", "new_node luôn trỏ về chính nó"),
		],
		correct="B", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "sll_next_pointer"], misconception_codes=["overwrite_before_linking"],
		misconception_by_answer={"A": "overwrite_before_linking", "C": "head_confusion", "D": "cycle_creation"},
		hint_ladder=[
			"Hãy xem node_k->next còn giữ giá trị successor cũ sau phép gán không.",
			"Một liên kết bị ghi đè có thể làm mất phần còn lại.",
		],
	),
	_item(
		"SLL-PILOT-G-04", "guided_practice", "mcq",
		"Trong đoạn chèn sau node_k, lỗi nào làm danh sách bị tách khỏi successor cũ?",
		difficulty="hard",
		options=[
			("A", "new_node->next = node_k->next; node_k->next = new_node"),
			("B", "node_k->next = new_node; new_node->next = nullptr"),
			("C", "new_node = node_k->next"),
			("D", "node_k = node_k->next"),
		],
		correct="B", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "kth_node_access", "sll_next_pointer"],
		misconception_codes=["lost_successor", "tail_boundary_confusion"],
		misconception_by_answer={"C": "head_confusion", "D": "wrong_k_boundary"},
		hint_ladder=["So sánh successor của new_node trong từng lựa chọn.", "new_node không nên trỏ nullptr nếu còn node phía sau."],
	),
	_item(
		"SLL-PILOT-I-01", "independent_checkpoint", "mcq",
		"Với head -> 2 -> 6 và k = 1, cặp liên kết đúng sau khi chèn 9 là gì?",
		difficulty="medium",
		options=[
			("A", "6->next = 9 và 9->next = nullptr"), ("B", "2->next = 9 và 9->next = 6"),
			("C", "9->next = 2 và 2->next = 6"), ("D", "head = 9 và 9->next = 2"),
		],
		correct="A", concepts=["sll_insertion_after_k", "kth_node_access"],
		prerequisites=["node_structure", "head_pointer", "traversal_counting"],
		misconception_codes=["off_by_one", "wrong_k_boundary"],
		misconception_by_answer={"B": "off_by_one", "C": "wrong_k_boundary", "D": "head_confusion"},
	),
	_item(
		"SLL-PILOT-I-02", "independent_checkpoint", "tracing",
		"Danh sách head -> 1 -> 4 -> 8. Chèn 6 sau vị trí k = 1. Hãy viết chuỗi kết quả.",
		difficulty="hard", correct="head -> 1 -> 4 -> 6 -> 8",
		concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "kth_node_access", "sll_next_pointer"], answer_mode="normalized_text",
		accepted_answers=["head->1->4->6->8", "head -> 1 -> 4 -> 6 -> 8", "1 -> 4 -> 6 -> 8"],
		misconception_codes=["off_by_one", "lost_successor"],
	),
	_item(
		"SLL-PILOT-R-01", "delayed_recheck", "mcq",
		"Khi chèn 10 sau node ở vị trí k, phép gán nào phải dùng successor cũ?",
		difficulty="medium",
		options=[
			("A", "new_node->next = node_k->next"), ("B", "node_k = new_node"),
			("C", "head = node_k"), ("D", "node_k->next = nullptr"),
		],
		correct="A", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "sll_next_pointer"],
		misconception_codes=["lost_successor", "wrong_statement_order"],
		misconception_by_answer={"B": "wrong_statement_order", "C": "head_confusion", "D": "tail_boundary_confusion"},
	),
	_item(
		"SLL-PILOT-R-02", "delayed_recheck", "mcq",
		"Chọn lỗi trong đoạn code làm mất phần còn lại của danh sách sau khi chèn.",
		difficulty="hard",
		options=[
			("A", "new_node->next = node_k->next; node_k->next = new_node"),
			("B", "node_k->next = new_node; new_node->next = node_k->next"),
			("C", "new_node->next = nullptr; node_k->next = new_node"),
			("D", "node_k = node_k->next; node_k->next = new_node"),
		],
		correct="B", concepts=["sll_insertion_after_k", "sll_next_pointer"],
		prerequisites=["node_structure", "kth_node_access", "sll_next_pointer"],
		misconception_codes=["overwrite_before_linking", "lost_successor"],
		misconception_by_answer={"C": "tail_boundary_confusion", "D": "wrong_k_boundary"},
	),
	_item(
		"SLL-PILOT-R-03", "delayed_recheck", "tracing",
		"Danh sách head -> 5 -> 9 -> 12. Chèn 7 sau k = 0. Hãy viết chuỗi sau cùng.",
		difficulty="medium", correct="head -> 5 -> 7 -> 9 -> 12",
		concepts=["sll_insertion_after_k", "kth_node_access"],
		prerequisites=["node_structure", "head_pointer", "traversal_counting"], answer_mode="normalized_text",
		accepted_answers=["head->5->7->9->12", "head -> 5 -> 7 -> 9 -> 12", "5 -> 7 -> 9 -> 12"],
		misconception_codes=["off_by_one", "lost_successor"],
	),
]


def items() -> list[dict[str, Any]]:
	"""Copies, so callers cannot mutate the frozen content."""
	return [dict(item) for item in ITEMS]


def item_codes_for_stage(stage: str) -> list[str]:
	return [item["code"] for item in ITEMS if item["stage"] == stage]
