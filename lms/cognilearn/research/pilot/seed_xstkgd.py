"""Seed the pilot course "Xác suất thống kê ứng dụng trong giáo dục – Chương 1" and its CL Study.

Native LMS questions only; every question restates its own data so any order works.
Run from frappe-bench/sites:  ../env/bin/python ../apps/lms/lms/cognilearn/research/pilot/seed_xstkgd.py
Then build the map once: bench --site <site> execute lms.cognilearn.adapters.events.map_course --kwargs '{"course": "<course>", "force": 1}'
"""

import json
import time

import frappe

frappe.init(site="lms.localhost", sites_path=".")
frappe.connect()
frappe.set_user("Administrator")

TITLE = "Xác suất thống kê ứng dụng trong giáo dục – Chương 1. Thống kê mô tả dữ liệu giáo dục"
STUDY_ID = "xstkgd_ch1_pilot_v1"
PREFIX = "XSTKGD C1"
INTRO = (
	"Chương mở đầu của học phần Xác suất thống kê ứng dụng trong giáo dục cho sinh viên năm nhất: "
	"thang đo, bảng tần số, số đo xu hướng trung tâm và độ phân tán, điểm chuẩn z, phân phối chuẩn trong đánh giá."
)


def q(text, options, correct, explain=None, wrong=None):
	"""options: list of str; correct: index; explain: shown on the right answer; wrong: {index: explanation}."""
	return {"text": text, "options": options, "correct": correct, "explain": explain, "wrong": wrong or {}}


SCALES = ["Định danh", "Thứ bậc", "Khoảng", "Tỉ lệ"]

BASELINE = [
	q("Mã số sinh viên được đo bằng thang đo nào?", SCALES, 0),
	q(
		"Khảo sát 40 sinh viên, có 14 người đi học bằng xe buýt. Tần suất của lựa chọn “xe buýt” là bao nhiêu?",
		["35%", "14%", "40%", "3,5%"],
		0,
	),
	q("Điểm của 5 sinh viên: 5, 6, 8, 9, 10. Trung vị của dãy điểm là bao nhiêu?", ["8", "7,6", "9", "7"], 0),
	q(
		"Điểm của 4 sinh viên (coi là toàn bộ tổng thể): 4, 6, 6, 8. Độ lệch chuẩn là bao nhiêu?",
		["≈ 1,41", "2", "≈ 1,63", "4"],
		0,
	),
	q(
		"Điểm thi có trung bình 5 và độ lệch chuẩn 2. Điểm z của một sinh viên được 8 điểm là bao nhiêu?",
		["1,5", "3", "4", "2"],
		0,
	),
	q(
		"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 6, độ lệch chuẩn 1. Khoảng bao nhiêu phần trăm thí sinh đạt dưới 5 điểm?",
		["≈ 16%", "≈ 32%", "≈ 34%", "≈ 5%"],
		0,
	),
]

RECHECK = [
	q("Thứ hạng của sinh viên trong lớp (hạng 1, hạng 2, hạng 3, …) được đo bằng thang đo nào?", SCALES, 1),
	q(
		"Khảo sát 50 sinh viên, có 20 người tự học trên 2 giờ mỗi ngày. Tần suất của nhóm này là bao nhiêu?",
		["40%", "20%", "50%", "2,5%"],
		0,
	),
	q(
		"Điểm của 6 sinh viên: 3, 5, 6, 8, 9, 10. Trung vị của dãy điểm là bao nhiêu?",
		["7", "6,83", "6", "8"],
		0,
	),
	q(
		"Điểm của 4 sinh viên (coi là toàn bộ tổng thể): 2, 4, 6, 8. Phương sai là bao nhiêu?",
		["5", "6,67", "≈ 2,24", "20"],
		0,
	),
	q(
		"Điểm thi có trung bình 60 và độ lệch chuẩn 8. Điểm z của một sinh viên được 48 điểm là bao nhiêu?",
		["−1,5", "1,5", "−12", "−0,67"],
		0,
	),
	q(
		"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 7, độ lệch chuẩn 1. Khoảng bao nhiêu phần trăm thí sinh đạt từ 5 đến 9 điểm?",
		["≈ 95%", "≈ 68%", "≈ 99,7%", "≈ 47,5%"],
		0,
	),
]

FREQ = "Điểm kiểm tra của một lớp 20 sinh viên: điểm 5 có 2 bạn, điểm 6 có 4 bạn, điểm 7 có 6 bạn, điểm 8 có 5 bạn, điểm 9 có 3 bạn."

LESSONS = [
	(
		"Dữ liệu giáo dục và thang đo",
		[
			"Biến định tính mô tả loại (giới tính, chuyên ngành); biến định lượng đo bằng con số có ý nghĩa (điểm thi, số buổi vắng).",
			"Biến định lượng rời rạc nhận các giá trị đếm được (số buổi vắng); biến định lượng liên tục có thể nhận mọi giá trị trong một khoảng (thời gian làm bài).",
			"Bốn thang đo: định danh (chỉ phân loại), thứ bậc (có thứ tự nhưng khoảng cách không đều), khoảng (khoảng cách đều, không có số 0 tuyệt đối), tỉ lệ (khoảng cách đều và có số 0 tuyệt đối).",
			"Thang đo quyết định phép tính nào có nghĩa: với dữ liệu định danh chỉ đếm được và tìm mốt; tính trung bình cần ít nhất thang khoảng.",
		],
		[
			q(
				"Giới tính của học sinh (nam, nữ) được đo bằng thang đo nào?",
				SCALES,
				0,
				"Chỉ phân loại, không có thứ tự: thang định danh.",
				{1: "Thứ bậc đòi hỏi các loại có thứ tự hơn kém; nam và nữ thì không."},
			),
			q(
				"Xếp loại học lực Giỏi – Khá – Trung bình – Yếu được đo bằng thang đo nào?",
				SCALES,
				1,
				"Có thứ tự nhưng khoảng cách giữa các loại không bằng nhau: thang thứ bậc.",
				{
					2: "Thang khoảng cần khoảng cách đều; từ Giỏi xuống Khá không chắc bằng từ Khá xuống Trung bình."
				},
			),
			q(
				"Số buổi vắng học của sinh viên trong một học kì được đo bằng thang đo nào?",
				SCALES,
				3,
				"Khoảng cách đều và có số 0 tuyệt đối (không vắng buổi nào): thang tỉ lệ.",
				{2: "Có số 0 tuyệt đối — vắng 4 buổi đúng là gấp đôi vắng 2 buổi — nên là thang tỉ lệ."},
			),
			q(
				"Biến nào sau đây là biến định lượng?",
				["Trường THPT đã học", "Điểm thi môn Toán", "Dân tộc", "Chuyên ngành đăng kí"],
				1,
				"Điểm thi là con số có ý nghĩa đo lường; các biến còn lại chỉ phân loại.",
			),
			q(
				"Có dữ liệu về chuyên ngành đăng kí của 200 tân sinh viên. Số đo nào dưới đây có ý nghĩa với dữ liệu này?",
				["Mốt", "Trung bình cộng", "Độ lệch chuẩn", "Trung vị"],
				0,
				"Chuyên ngành là thang định danh: chỉ đếm được, nên chỉ mốt (chuyên ngành nhiều người chọn nhất) có nghĩa.",
				{3: "Trung vị cần sắp thứ tự, mà các chuyên ngành không có thứ tự."},
			),
			q(
				"Số anh chị em ruột của một học sinh là loại biến nào?",
				["Định lượng rời rạc", "Định lượng liên tục", "Định tính", "Không phải là biến"],
				0,
				"Giá trị đếm được 0, 1, 2, …: biến định lượng rời rạc.",
				{1: "Không thể có 1,5 anh chị em; biến liên tục mới nhận mọi giá trị trong một khoảng."},
			),
			q(
				"Thời gian (phút) sinh viên hoàn thành một bài kiểm tra là loại biến nào?",
				["Định lượng liên tục", "Định lượng rời rạc", "Định tính", "Không phải là biến"],
				0,
				"Thời gian có thể nhận mọi giá trị trong một khoảng (12,5 phút, 12,75 phút…): biến liên tục.",
				{1: "Làm tròn khi ghi chép không làm biến trở thành rời rạc."},
			),
			q(
				"Biến nào sau đây là biến định tính?",
				[
					"Hình thức học (trực tiếp, trực tuyến)",
					"Số giờ tự học mỗi tuần",
					"Điểm trung bình tích lũy",
					"Số tín chỉ đã đăng kí",
				],
				0,
				"Hình thức học chỉ phân loại; ba biến còn lại là con số đo lường.",
			),
		],
	),
	(
		"Bảng tần số và tần suất",
		[
			"Tần số là số lần một giá trị xuất hiện; tần suất = tần số / tổng số quan sát, thường ghi theo phần trăm.",
			"Tần suất tích lũy đến một giá trị là tỉ lệ quan sát không vượt quá giá trị đó — trả lời câu hỏi “bao nhiêu phần trăm đạt không quá…”.",
		],
		[
			q(
				f"{FREQ} Tần suất của điểm 7 là bao nhiêu?",
				["30%", "6%", "35%", "20%"],
				0,
				"6 / 20 = 30%.",
				{1: "6 là tần số (số bạn), chưa chia cho tổng 20 bạn."},
			),
			q(
				f"{FREQ} Bao nhiêu phần trăm sinh viên đạt từ 8 điểm trở lên?",
				["40%", "25%", "15%", "8%"],
				0,
				"(5 + 3) / 20 = 40%.",
				{1: "25% chỉ tính điểm 8, còn thiếu 3 bạn điểm 9."},
			),
			q(
				f"{FREQ} Tần suất tích lũy đến điểm 7 (tỉ lệ sinh viên đạt không quá 7 điểm) là bao nhiêu?",
				["60%", "30%", "40%", "12%"],
				0,
				"(2 + 4 + 6) / 20 = 60%.",
				{1: "30% chỉ là tần suất của riêng điểm 7.", 3: "12 là tần số tích lũy, chưa chia cho 20."},
			),
			q(
				"Khảo sát 200 sinh viên về mức độ hài lòng với thư viện, có 50 người chọn “Rất hài lòng”. Tần suất của lựa chọn này là bao nhiêu?",
				["25%", "50%", "4%", "0,5%"],
				0,
				"50 / 200 = 25%.",
				{2: "4 là 200 / 50: chia ngược."},
			),
			q(
				"Điểm của 50 sinh viên: dưới 5 điểm có 5 bạn, từ 5 đến dưới 7 có 20 bạn, từ 7 đến dưới 9 có 18 bạn, từ 9 trở lên có 7 bạn. Tần suất tích lũy của nhóm dưới 7 điểm là bao nhiêu?",
				["50%", "40%", "25%", "10%"],
				0,
				"(5 + 20) / 50 = 50%.",
				{1: "40% chỉ là nhóm từ 5 đến dưới 7, quên cộng nhóm dưới 5."},
			),
			q(
				"Theo bảng tần suất tích lũy điểm của một lớp: 35% sinh viên đạt không quá 6 điểm, 80% đạt không quá 8 điểm. Tỉ lệ sinh viên đạt trên 6 và không quá 8 điểm là bao nhiêu?",
				["45%", "80%", "115%", "35%"],
				0,
				"80% − 35% = 45%.",
				{2: "Tần suất tích lũy không cộng dồn thêm lần nữa; tỉ lệ không thể vượt 100%."},
			),
			q(
				"Tần suất tích lũy đến giá trị lớn nhất của một dãy số liệu luôn bằng bao nhiêu?",
				["100%", "50%", "Tần suất của giá trị lớn nhất", "Không xác định được"],
				0,
				"Mọi quan sát đều không vượt quá giá trị lớn nhất nên tỉ lệ là 100%.",
			),
		],
	),
	(
		"Số đo xu hướng trung tâm",
		[
			"Trung bình cộng = tổng các giá trị / số giá trị. Trung bình có trọng số: nhân mỗi giá trị với trọng số của nó (ví dụ số tín chỉ) rồi chia cho tổng trọng số.",
			"Trung vị là giá trị đứng giữa khi sắp xếp dãy tăng dần; với số lượng chẵn, lấy trung bình của hai giá trị giữa. Trung vị ít bị ảnh hưởng bởi giá trị ngoại lai.",
			"Mốt là giá trị xuất hiện nhiều nhất.",
		],
		[
			q(
				"Điểm 5 bài kiểm tra của một sinh viên: 6, 7, 8, 8, 9. Điểm trung bình là bao nhiêu?",
				["7,6", "8", "7,5", "8,5"],
				0,
				"(6 + 7 + 8 + 8 + 9) / 5 = 38 / 5 = 7,6.",
				{1: "8 là trung vị (và mốt) của dãy, không phải trung bình."},
			),
			q(
				"Điểm của 6 sinh viên: 4, 6, 7, 8, 9, 10. Trung vị của dãy điểm là bao nhiêu?",
				["7,5", "7", "8", "≈ 7,33"],
				0,
				"Số lượng chẵn: trung bình hai giá trị giữa (7 + 8) / 2 = 7,5.",
				{3: "≈ 7,33 là trung bình cộng của cả dãy."},
			),
			q(
				"Một sinh viên được 8 điểm ở học phần 3 tín chỉ và 6 điểm ở học phần 2 tín chỉ. Điểm trung bình có trọng số theo tín chỉ là bao nhiêu?",
				["7,2", "7", "7,5", "6,8"],
				0,
				"(8 · 3 + 6 · 2) / (3 + 2) = 36 / 5 = 7,2.",
				{1: "7 là trung bình cộng thường, quên trọng số tín chỉ."},
			),
			q(
				"Điểm của 7 sinh viên: 5, 6, 6, 7, 7, 7, 10. Mốt của dãy điểm là bao nhiêu?",
				["7", "6", "≈ 6,86", "10"],
				0,
				"Điểm 7 xuất hiện nhiều nhất (3 lần).",
				{2: "≈ 6,86 là trung bình cộng, không phải mốt."},
			),
			q(
				"Điểm của một nhóm 5 sinh viên: 6, 7, 7, 8 và 0 (một bạn bỏ thi). Số đo nào ít bị ảnh hưởng bởi điểm 0 nhất?",
				["Trung vị", "Trung bình cộng", "Khoảng biến thiên", "Tổng điểm"],
				0,
				"Trung vị chỉ phụ thuộc vị trí giữa (vẫn là 7); trung bình tụt từ 7 xuống 5,6.",
				{1: "Trung bình cộng dùng mọi giá trị nên bị điểm 0 kéo xuống mạnh."},
			),
			q(
				"Khảo sát phương tiện đến trường của 30 sinh viên: xe máy 12 người, xe buýt 10 người, xe đạp 8 người. Mốt của dữ liệu này là gì?",
				["Xe máy", "12", "Xe buýt", "10"],
				0,
				"Mốt là giá trị xuất hiện nhiều nhất: xe máy.",
				{1: "12 là tần số của mốt, không phải mốt."},
			),
			q(
				"Điểm của 6 sinh viên: 5, 5, 6, 8, 8, 9. Mốt của dãy điểm là gì?",
				["5 và 8", "5", "8", "Không có mốt"],
				0,
				"Điểm 5 và điểm 8 cùng xuất hiện 2 lần, nhiều nhất: dãy có hai mốt.",
				{3: "Dãy vẫn có mốt; chỉ là có hai giá trị cùng xuất hiện nhiều nhất."},
			),
		],
	),
	(
		"Số đo độ phân tán",
		[
			"Khoảng biến thiên = giá trị lớn nhất − giá trị nhỏ nhất.",
			"Phương sai tổng thể = trung bình của bình phương độ lệch so với trung bình (chia cho n); phương sai mẫu chia cho n − 1. Độ lệch chuẩn là căn bậc hai của phương sai.",
			"Cùng trung bình, nhóm có độ lệch chuẩn nhỏ hơn thì đồng đều hơn.",
		],
		[
			q(
				"Điểm của 5 sinh viên: 4, 6, 7, 9, 10. Khoảng biến thiên là bao nhiêu?",
				["6", "7,2", "10", "3"],
				0,
				"10 − 4 = 6.",
				{1: "7,2 là trung bình cộng."},
			),
			q(
				"Điểm của 4 sinh viên (coi là toàn bộ tổng thể): 5, 7, 7, 9. Phương sai là bao nhiêu?",
				["2", "≈ 2,67", "≈ 1,41", "8"],
				0,
				"Trung bình 7; bình phương độ lệch 4, 0, 0, 4; tổng 8 chia 4 = 2.",
				{
					1: "Chia cho n − 1 = 3 là phương sai mẫu; đề bài coi 4 bạn là toàn bộ tổng thể.",
					2: "≈ 1,41 là độ lệch chuẩn, căn bậc hai của phương sai.",
				},
			),
			q(
				"Phương sai điểm của một lớp là 2,25. Độ lệch chuẩn là bao nhiêu?",
				["1,5", "≈ 5,06", "1,125", "2,25"],
				0,
				"√2,25 = 1,5.",
				{1: "≈ 5,06 là bình phương, ngược chiều với khai căn."},
			),
			q(
				"Lớp A và lớp B có cùng điểm trung bình 7; độ lệch chuẩn lần lượt là 0,8 và 2,1. Nhận xét nào đúng?",
				[
					"Điểm lớp A đồng đều hơn lớp B",
					"Điểm lớp B đồng đều hơn lớp A",
					"Hai lớp đồng đều như nhau vì cùng trung bình",
					"Lớp B học tốt hơn lớp A",
				],
				0,
				"Độ lệch chuẩn nhỏ hơn nghĩa là điểm tập trung sát trung bình hơn.",
				{2: "Cùng trung bình không có nghĩa là cùng mức phân tán."},
			),
			q(
				"Điểm của 4 sinh viên đều là 6. Độ lệch chuẩn của dãy điểm là bao nhiêu?",
				["0", "6", "1", "24"],
				0,
				"Mọi giá trị bằng trung bình nên không có độ lệch: độ lệch chuẩn bằng 0.",
			),
			q(
				"Điểm của hai nhóm: nhóm A được 5, 6, 7; nhóm B được 2, 6, 10. Khoảng biến thiên của nhóm B lớn hơn của nhóm A bao nhiêu?",
				["6", "8", "2", "0"],
				0,
				"Nhóm A: 7 − 5 = 2; nhóm B: 10 − 2 = 8; chênh 6.",
				{3: "Hai nhóm cùng trung bình 6 nhưng độ phân tán rất khác."},
			),
			q(
				"Điểm của 6 sinh viên: 3, 7, 7, 8, 8, 9. Nếu bỏ bạn được 3 điểm, khoảng biến thiên thay đổi thế nào?",
				["Giảm từ 6 xuống 2", "Không đổi", "Giảm từ 6 xuống 5", "Tăng lên"],
				0,
				"Trước: 9 − 3 = 6; sau: 9 − 7 = 2. Khoảng biến thiên rất nhạy với giá trị ngoại lai.",
			),
			q(
				"Một lớp có điểm cao nhất là 9,5 và khoảng biến thiên là 6. Điểm thấp nhất của lớp là bao nhiêu?",
				["3,5", "15,5", "6", "4"],
				0,
				"Thấp nhất = cao nhất − khoảng biến thiên = 9,5 − 6 = 3,5.",
				{1: "Cộng thay vì trừ; điểm không thể vượt thang 10."},
			),
		],
	),
	(
		"Điểm chuẩn z",
		[
			"Điểm z = (x − trung bình) / độ lệch chuẩn: cho biết một kết quả cách trung bình bao nhiêu độ lệch chuẩn, về phía trên (z > 0) hay phía dưới (z < 0).",
			"Điểm z giúp so sánh kết quả giữa các bài thi có thang điểm hoặc độ khó khác nhau. Điểm T = 50 + 10z là một cách đổi z sang thang dễ đọc.",
		],
		[
			q(
				"Điểm thi có trung bình 6 và độ lệch chuẩn 1,5. Điểm z của một sinh viên được 9 điểm là bao nhiêu?",
				["2", "3", "1,5", "0,5"],
				0,
				"(9 − 6) / 1,5 = 2.",
				{1: "3 là độ chênh so với trung bình, chưa chia cho độ lệch chuẩn."},
			),
			q(
				"Điểm thi có trung bình 7 và độ lệch chuẩn 2. Một sinh viên có điểm z = −1. Điểm thô của sinh viên là bao nhiêu?",
				["5", "9", "6", "−2"],
				0,
				"x = 7 + (−1) · 2 = 5.",
				{1: "z âm nghĩa là dưới trung bình, nên phải trừ."},
			),
			q(
				"An được 8 điểm Toán (lớp có trung bình 6, độ lệch chuẩn 2) và 7 điểm Văn (lớp có trung bình 5, độ lệch chuẩn 1). So với lớp, An làm tốt hơn ở môn nào?",
				["Văn", "Toán", "Như nhau", "Không so sánh được"],
				0,
				"z Toán = (8 − 6) / 2 = 1; z Văn = (7 − 5) / 1 = 2: so với lớp, An làm Văn tốt hơn.",
				{
					1: "Chỉ nhìn điểm thô; cần so theo độ lệch chuẩn của từng lớp.",
					3: "Điểm z chính là công cụ để so sánh được.",
				},
			),
			q(
				"Điểm T được tính bằng T = 50 + 10z. Một sinh viên có z = 1,5 thì điểm T là bao nhiêu?",
				["65", "51,5", "60", "15"],
				0,
				"50 + 10 · 1,5 = 65.",
				{1: "Quên nhân z với 10."},
			),
		],
	),
	(
		"Phân phối chuẩn trong đánh giá",
		[
			"Điểm của một kì thi lớn thường có phân phối xấp xỉ chuẩn: hình chuông, đối xứng quanh trung bình; trung bình, trung vị và mốt bằng nhau.",
			"Quy tắc 68 – 95 – 99,7: khoảng 68% giá trị nằm trong ±1 độ lệch chuẩn quanh trung bình, 95% trong ±2 và 99,7% trong ±3.",
			"Nhờ đối xứng, mỗi phía ngoài ±1 độ lệch chuẩn có khoảng 16%, ngoài ±2 có khoảng 2,5%. Ví dụ z = 1 ứng với bách phân vị thứ 84.",
		],
		[
			q(
				"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 6, độ lệch chuẩn 1. Khoảng bao nhiêu phần trăm thí sinh đạt từ 5 đến 7 điểm?",
				["≈ 68%", "≈ 95%", "≈ 50%", "≈ 34%"],
				0,
				"Từ 5 đến 7 là ±1 độ lệch chuẩn: khoảng 68%.",
				{3: "34% chỉ là một nửa, từ 6 đến 7."},
			),
			q(
				"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 500, độ lệch chuẩn 100. Khoảng bao nhiêu phần trăm thí sinh đạt trên 700 điểm?",
				["≈ 2,5%", "≈ 5%", "≈ 16%", "≈ 0,15%"],
				0,
				"700 là +2 độ lệch chuẩn; 5% nằm ngoài ±2, chia đều hai phía: 2,5%.",
				{1: "5% là cả hai phía (dưới 300 và trên 700)."},
			),
			q(
				"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 7, độ lệch chuẩn 1. Một sinh viên được 8 điểm thì xấp xỉ ở bách phân vị thứ mấy?",
				["84", "68", "50", "16"],
				0,
				"z = 1: 50% dưới trung bình cộng 34% từ 7 đến 8 = 84%.",
				{1: "68% là tỉ lệ trong khoảng ±1 độ lệch chuẩn, không phải tỉ lệ dưới 8 điểm."},
			),
			q(
				"Trong một phân phối chuẩn, trung bình, trung vị và mốt có quan hệ thế nào?",
				[
					"Bằng nhau",
					"Trung bình > trung vị > mốt",
					"Mốt > trung vị > trung bình",
					"Không xác định được",
				],
				0,
				"Phân phối chuẩn đối xứng quanh đỉnh nên ba số đo trùng nhau.",
			),
			q(
				"Điểm một kì thi có phân phối xấp xỉ chuẩn, trung bình 6, độ lệch chuẩn 1,5. Khoảng 95% thí sinh có điểm trong khoảng nào?",
				["Từ 3 đến 9", "Từ 4,5 đến 7,5", "Từ 1,5 đến 10,5", "Từ 6 đến 9"],
				0,
				"±2 độ lệch chuẩn: 6 ± 3.",
				{1: "Đó là ±1 độ lệch chuẩn, chứa khoảng 68%."},
			),
		],
	),
]


def para(text):
	return {"type": "paragraph", "data": {"text": text}}


def quiz_block(name):
	return {"type": "quiz", "data": {"quiz": name}}


def content(*blocks):
	return json.dumps(
		{"time": int(time.time() * 1000), "blocks": list(blocks), "version": "2.29.0"}, ensure_ascii=False
	)


def make_question(spec):
	doc = {"doctype": "LMS Question", "question": f"<p>{spec['text']}</p>", "type": "Choices", "multiple": 0}
	for index, option in enumerate(spec["options"], start=1):
		doc[f"option_{index}"] = option
		doc[f"is_correct_{index}"] = int(index - 1 == spec["correct"])
		if index - 1 == spec["correct"] and spec["explain"]:
			doc[f"explanation_{index}"] = spec["explain"]
		elif (index - 1) in spec["wrong"]:
			doc[f"explanation_{index}"] = spec["wrong"][index - 1]
	return frappe.get_doc(doc).insert().name


def make_quiz(title, specs, *, course, show_answers):
	return frappe.get_doc(
		{
			"doctype": "LMS Quiz",
			"title": title,
			"course": course,
			"show_answers": show_answers,
			"max_attempts": 1 if not show_answers else 0,
			"passing_percentage": 0,
			"questions": [{"question": make_question(spec), "marks": 1, "type": "Choices"} for spec in specs],
		}
	).insert()


def add_chapter(course, title, lessons):
	chapter = frappe.get_doc({"doctype": "Course Chapter", "course": course.name, "title": title}).insert()
	names = []
	for lesson_title, body in lessons:
		lesson = frappe.get_doc(
			{
				"doctype": "Course Lesson",
				"course": course.name,
				"chapter": chapter.name,
				"title": lesson_title,
				"content": body,
			}
		).insert()
		chapter.append("lessons", {"lesson": lesson.name})
		names.append(lesson.name)
	chapter.save()
	course.reload()
	course.append("chapters", {"chapter": chapter.name})
	course.save()
	return names


if frappe.db.get_value("LMS Course", {"title": TITLE}):
	raise SystemExit(f"exists: {frappe.db.get_value('LMS Course', {'title': TITLE})}")

# Only one pilot study runs: retire the earlier probability draft (kept, unpublished, reversible).
for old in frappe.get_all("CL Study", filters={"active": 1}, fields=["name", "course"]):
	frappe.db.set_value("CL Study", old.name, "active", 0)
	frappe.db.set_value("LMS Course", old.course, "published", 0)

# Mapping runs once, after everything is in place.
auto_map = frappe.get_single("CL Settings").auto_map_on_change
frappe.db.set_single_value("CL Settings", "auto_map_on_change", 0)

course = frappe.get_doc(
	{
		"doctype": "LMS Course",
		"title": TITLE,
		"short_introduction": INTRO,
		"description": "<p>Khóa pilot của CogniLearn. Nội dung và câu hỏi do nhóm nghiên cứu soạn; giáo viên phụ trách duyệt lại trước khi dùng.</p>",
		"instructors": [{"instructor": "Administrator"}],
		"published": 1,
	}
).insert()

baseline = make_quiz(f"{PREFIX} – Kiểm tra đầu vào", BASELINE, course=course.name, show_answers=0)
recheck = make_quiz(f"{PREFIX} – Kiểm tra lại", RECHECK, course=course.name, show_answers=0)

add_chapter(
	course,
	"Kiểm tra đầu vào",
	[
		(
			"Bài kiểm tra đầu vào",
			content(
				para(
					"Sáu câu tự làm, không xem đáp án. Kết quả giúp hệ thống biết bạn đang vững và còn hổng ở đâu."
				),
				quiz_block(baseline.name),
			),
		)
	],
)
lesson_names = add_chapter(
	course,
	"Thống kê mô tả dữ liệu giáo dục",
	[
		(
			title,
			content(
				*[para(t) for t in theory], para("Luyện tập: mở trang Luyện tập CogniLearn của khóa học.")
			),
		)
		for title, theory, _ in LESSONS
	],
)
for (title, _theory, specs), lesson in zip(LESSONS, lesson_names, strict=True):
	bank = make_quiz(f"{PREFIX} – Ngân hàng: {title}", specs, course=course.name, show_answers=1)
	frappe.db.set_value("LMS Quiz", bank.name, "lesson", lesson)
add_chapter(
	course,
	"Kiểm tra lại sau 3 ngày",
	[
		(
			"Bài kiểm tra lại",
			content(
				para("Sáu câu tự làm để đo khả năng ghi nhớ sau vài ngày. Hệ thống sẽ báo khi đến lúc làm."),
				quiz_block(recheck.name),
			),
		)
	],
)

frappe.get_doc(
	{
		"doctype": "CL Study",
		"study_id": STUDY_ID,
		"course": course.name,
		"active": 1,
		"baseline_quiz": baseline.name,
		"recheck_quiz": recheck.name,
		"set_size": 4,
		"budget_sets": 3,
		"recheck_delay_hours": 72,
	}
).insert()
frappe.db.set_single_value("CL Settings", "auto_map_on_change", auto_map)
frappe.db.commit()
print(
	json.dumps(
		{"course": course.name, "baseline": baseline.name, "recheck": recheck.name, "lessons": lesson_names},
		ensure_ascii=False,
	)
)
frappe.destroy()
