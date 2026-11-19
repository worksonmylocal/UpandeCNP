from frappe.tests.utils import FrappeTestCase

from upandecnp.upandecnp.utils.micro_programme import block_kg, kg_per_tree


class TestMicroProgrammeMaths(FrappeTestCase):
	"""The figures on the agronomist's own Borax sheet (20 kg/ha, 250 trees/ha)."""

	def test_kg_per_tree(self):
		self.assertEqual(kg_per_tree(20), 0.08)

	def test_block_quantities_match_the_sheet(self):
		for trees, kg in [(534, 42.7), (519, 41.5), (656, 52.5), (584, 46.7),
		                  (527, 42.2), (777, 62.2), (13996, 1119.7)]:
			self.assertEqual(block_kg(trees, 20), kg)

	def test_a_different_density_changes_the_per_tree_dose(self):
		self.assertEqual(kg_per_tree(20, 200), 0.1)
		self.assertEqual(block_kg(100, 20, 200), 10.0)
