# Copyright (c) 2026, CogniLearn contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CLEvidence(Document):
	def validate(self):
		# The evidence log is the single source of truth; the learner model is recomputed from it.
		if not self.is_new():
			frappe.throw("CL Evidence is append-only.")
