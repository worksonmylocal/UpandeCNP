import frappe
from frappe.model.document import Document


class FertilizerProduct(Document):
	def validate(self):
		if not self.terms():
			frappe.throw("Give at least one search term, otherwise no Items can ever match this product.")


	def terms(self):
		return _split(self.search_terms)

	def excludes(self):
		return _split(self.exclude_terms)


def _split(text):
	"""Terms may be written one per line or comma separated - accept both,
	since agronomists edit this field by hand."""
	if not text:
		return []
	parts = []
	for line in str(text).replace(",", "\n").splitlines():
		line = line.strip()
		if line:
			parts.append(line)
	return parts
