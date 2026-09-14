import frappe
from upandecnp.upandecnp.utils.calculation_engine import calculate_programme
from upandecnp.upandecnp.api import load_programme_products


def run():
    out=[]
    src=frappe.get_doc("Fertilizer Programme", frappe.get_all("Fertilizer Programme",limit=1)[0].name)
    d=frappe.copy_doc(src); d.season="TESTSWAP"; d.insert(ignore_permissions=True)
    load_programme_products(d.name); d.reload()

    # Reproduce the live situation: pick the K2SO4 Item the Production
    # Calendar knows NOTHING about (live's best-stocked one), while the
    # potassium source rule still points at the calendar's item.
    swapped=None
    for r in d.get("product_selections"):
        if r.product=="K2SO4":
            r.fertilizer_item="1010100015"   # not in any Fertilizer Schedule row
            swapped=r.fertilizer_item
    d.save()
    cal_items={s.fertilizer_product for s in
               frappe.get_doc("Production Calendar", d.production_calendar).get("fertilizer_schedule")}
    out.append(f"  chosen K2SO4 item : {swapped}")
    out.append(f"  in calendar?      : {swapped in cal_items}  (calendar items: {sorted(cal_items)})")

    n=calculate_programme(d.name); d.reload()
    lines=[l for l in d.get("programme_lines") if l.fertilizer_product==swapped]
    months=sorted({l.application_month for l in lines})
    out.append(f"\n  RESULT: {n} lines generated, {len(lines)} of them for the swapped item")
    out.append(f"  months for swapped item: {months}")
    out.append(f"  total kg swapped item : {sum(l.total_kg for l in lines):,.0f}")
    for r in d.get("product_selections"):
        out.append(f"    {r.product:<6} item={r.fertilizer_item:<13} required={r.required_qty:>11,.0f} "
                   f"stock={r.available_qty:>11,.0f} short={r.shortfall:>10,.0f}")

    frappe.delete_doc("Fertilizer Programme", d.name, force=True, ignore_permissions=True)
    frappe.db.commit()
    out.append("\n  (test draft deleted)")
    print("\n".join(out))
