"""Fertilizer Store Request is retired in favour of a standard Material Request
(type Material Issue) - this field keeps the Material Request traceable back to
the Block Fertilizer Plan it was raised for, the same way the old
Fertilizer Store Request.block_fertilizer_plan link did."""

import frappe


def execute():
	from upandecnp.upandecnp.install import create_material_request_custom_field

	create_material_request_custom_field()
