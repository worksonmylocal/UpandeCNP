"""Adds the per-farm Agronomist roles for sites that installed upandecnp
before farm-based data segregation existed."""

import frappe


def execute():
	from upandecnp.upandecnp.install import create_roles

	create_roles()
