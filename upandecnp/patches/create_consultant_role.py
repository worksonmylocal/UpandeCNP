"""Adds the CNP Consultant role for sites that installed upandecnp before the
Fertilizer Programme approval chain existed.

create_roles() is only called on install, and the earlier role patch has
already run on these sites, so a patch of its own is what carries the new role
across. The approval workflow will not generate without it - its transitions
name the role, and a Workflow Transition's role is a Link.
"""

import frappe


def execute():
	from upandecnp.upandecnp.install import create_roles

	create_roles()

	from upandecnp.upandecnp.utils.approval import build_workflow

	name = build_workflow()
	if name:
		print(f"UpandeCNP: built workflow {name}")
