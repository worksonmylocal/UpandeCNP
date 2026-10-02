import frappe
from upandecnp.upandecnp import api


def run():
    out=[]
    def show(label, rows, keys, n=3):
        out.append(f"\n  {label}: {len(rows) if isinstance(rows,list) else '?'} rows")
        for r in (rows or [])[:n]:
            out.append("     " + " | ".join(f"{k}={r.get(k)}" for k in keys if k in r))

    show("search_fertilizer_items('pota')", api.search_fertilizer_items(search="pota"),
         ["item_code","item_name","stock_qty"])
    blocks=api.get_desk_blocks()
    show("get_desk_blocks", blocks, ["block","section","rounds","done","pct","state","last_yield"])
    if blocks:
        d=api.get_block_detail(blocks[0]["block"])
        out.append(f"\n  get_block_detail({blocks[0]['block']}):")
        out.append(f"     rounds={d['rounds']} done={d['done']} pct={d['pct']} "
                   f"planned={d['planned_kg']} actual={d['actual_kg']}")
        out.append(f"     yield: block={d['yield']['block']} farm_avg={d['yield']['farm_avg']} "
                   f"best={d['yield']['farm_best']} vs_avg={d['yield']['vs_avg_pct']}%")
        out.append(f"     plans={len(d['plans'])} applied={len(d['applied'])}")
    show("get_desk_store_requests", api.get_desk_store_requests(),
         ["name","block","employee_name","qty","state"])
    show("get_desk_applications", api.get_desk_applications(),
         ["name","block","application_date","actual_quantity_applied_kg","supervisor_name"])
    v=api.get_variance_by_section()
    show("get_variance_by_section", v, ["section","planned","actual","variance","pct","blocks"])
    if v:
        show(f"get_variance_by_block({v[0]['section']})",
             api.get_variance_by_block(v[0]["section"]), ["block","planned","actual","pct"])
    show("get_desk_stock", api.get_desk_stock(),
         ["item_name","stock","required","shortfall","sufficient","in_programme"], 5)
    print("\n".join(out))
