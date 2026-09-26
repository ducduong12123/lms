# Copyright (c) 2026, CogniLearn contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CLDecisionLog(Document):
	def validate(self):
		# PT4 learns from these rows later, so a decision is never rewritten after the fact.
		if not self.is_new():
			frappe.throw("CL Decision Log is append-only.")
