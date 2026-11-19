from frappe.model.document import Document


class CorrectionRequest(Document):
	"""A supervisor's request to change the quantity on a submitted Fertilizer
	Application or store request. Nothing here changes the original: only an
	approver can, through upandecnp.upandecnp.utils.corrections."""
