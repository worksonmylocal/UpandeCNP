"""Adds the roles the Fertilizer Programme approval chain needs, for sites
that installed upandecnp before it existed.

create_roles() is only called on install and the earlier role patch has already
run on these sites, so a patch of its own is what carries new roles across. The
workflow will not generate without them - a Workflow Transition's role is a
Link, so every role it names has to exist first.

No consultant role is shipped: that step sits with an existing role until the
agronomy consultant has an account. See utils/approval.py.
"""

import frappe


def execute():
	from upandecnp.upandecnp.install import create_roles

	create_roles()

	from upandecnp.upandecnp.utils.approval import build_workflow

	name = build_workflow()
	if name:
		print(f"UpandeCNP: built workflow {name}")
