/* Agronomist Desk.
 *
 * One page for the whole job: build the season's programme, choose what it will
 * actually be drawn from, calculate it, send it for review, then follow the
 * plans, requests and applications it produces. The agronomist never opens a
 * doctype form, which is the point - the forms expose every field in the
 * schema, in schema order, with no idea which step comes next.
 *
 * Follows the clinic desk's shape: KPIs, pill tabs, and queues whose rows carry
 * the action that moves the work on. */

(function () {
  const cfg = window.CNP || {};
  const $  = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n, d = 0) => (Number(n) || 0).toLocaleString(undefined,
    { minimumFractionDigits: d, maximumFractionDigits: d });

  let state = { farm: "", season: "", data: null };

  // ------------------------------------------------------------------ transport
  async function call(method, args = {}, { quiet = false } = {}) {
    let res, data;
    try {
      res = await fetch("/api/method/upandecnp.upandecnp.api." + method, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Frappe-CSRF-Token": cfg.csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify(args),
      });
      data = await res.json();
    } catch (e) {
      if (!quiet) toast("Could not reach the server.", "bad");
      throw Object.assign(new Error("network"), { handled: true });
    }
    if (!res.ok || data.exc) {
      if (res.status === 401 || res.status === 403) {
        location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname);
      }
      const msg = serverMessage(data) || `Server error (${res.status}).`;
      if (!quiet) toast(msg, "bad");
      throw Object.assign(new Error(msg), { handled: true });
    }
    return data.message;
  }

  /** Frappe buries the useful sentence inside _server_messages. */
  function serverMessage(d) {
    try {
      if (d && d._server_messages) {
        const first = JSON.parse(d._server_messages)[0];
        const parsed = typeof first === "string" ? JSON.parse(first) : first;
        if (parsed && parsed.message) return String(parsed.message).replace(/<[^>]+>/g, "");
      }
    } catch (e) { /* fall through */ }
    if (d && d.exception) return String(d.exception).split(":").pop().trim();
    return null;
  }

  let toastTimer;
  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " toast--" + kind : "");
    el.textContent = msg;
    document.body.appendChild(el);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.remove(), 4200);
  }

  // --------------------------------------------------------------- frappe client
  /** Generic document calls. These are Frappe's own whitelisted endpoints, so
   *  permissions, validation and the doctype's own controller all still run -
   *  the desk is a nicer way in, not a way round. */
  async function doc(method, args) {
    let res, data;
    try {
      res = await fetch("/api/method/frappe.client." + method, {
        method: "POST",
        headers: {
          "Content-Type": "application/json", Accept: "application/json",
          "X-Frappe-CSRF-Token": cfg.csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify(args),
      });
      data = await res.json();
    } catch (e) {
      toast("Could not reach the server.", "bad");
      throw Object.assign(new Error("network"), { handled: true });
    }
    if (!res.ok || data.exc) {
      const msg = serverMessage(data) || `Server error (${res.status}).`;
      toast(msg, "bad");
      throw Object.assign(new Error(msg), { handled: true });
    }
    return data.message;
  }

  const getDoc  = (doctype, name) => doc("get", { doctype, name });
  const listDoc = (doctype, fields, filters, order) =>
    doc("get_list", {
      doctype, fields, filters: filters || [],
      order_by: order || "modified desc", limit_page_length: 200,
    });
  const saveDoc = (d) => doc(d.name && !d.__islocal ? "save" : "insert", { doc: d });

  // ----------------------------------------------------------------- modal/form
  let openModals = 0;

  function modal({ title, sub = "", body = "", foot = [], size = "", onClose }) {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `<div class="modal ${size ? "modal--" + size : ""}" role="dialog" aria-modal="true">
      <div class="modal__head"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div>
      <button class="modal__x" aria-label="Close">&times;</button></div>
      <div class="modal__body"></div><div class="modal__foot"></div></div>`;
    document.body.appendChild(back);
    openModals++;
    const bodyEl = $(".modal__body", back), footEl = $(".modal__foot", back);
    if (typeof body === "string") bodyEl.innerHTML = body; else bodyEl.appendChild(body);

    const handle = {
      el: back, body: bodyEl, foot: footEl,
      close() {
        if (!back.isConnected) return;
        back.remove(); openModals--;
        document.removeEventListener("keydown", onKey);
        if (onClose) onClose();
      },
      setFoot(buttons) {
        footEl.innerHTML = "";
        buttons.forEach((b) => {
          const btn = document.createElement("button");
          btn.className = "btn " + (b.cls || "");
          btn.textContent = b.label;
          btn.addEventListener("click", async () => {
            if (!b.onClick) return handle.close();
            const all = $$("button", footEl);
            all.forEach((x) => (x.disabled = true));
            try { await b.onClick(handle); }
            catch (e) { if (!e.handled) toast(e.message || "Something went wrong.", "bad"); }
            finally { if (back.isConnected) all.forEach((x) => (x.disabled = false)); }
          });
          footEl.appendChild(btn);
        });
        footEl.style.display = buttons.length ? "" : "none";
      },
    };
    const onKey = (e) => { if (e.key === "Escape") handle.close(); };
    document.addEventListener("keydown", onKey);
    $(".modal__x", back).addEventListener("click", () => handle.close());
    handle.setFoot(foot);
    return handle;
  }

  /** One labelled input. `link` fetches its options once, lazily. */
  function fieldHtml(f, value) {
    const v = value == null ? "" : value;
    const req = f.reqd ? ` <span class="req">*</span>` : "";
    let input;
    if (f.type === "select") {
      input = `<select data-f="${esc(f.name)}">${(f.options || []).map((o) =>
        `<option value="${esc(o)}"${String(o) === String(v) ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
    } else if (f.type === "link") {
      input = `<select data-f="${esc(f.name)}" data-link="${esc(f.doctype)}" data-val="${esc(v)}">
        <option value="${esc(v)}">${esc(v || "—")}</option></select>`;
    } else if (f.type === "itempick") {
      // Shows the name, stores the code. Nobody recognises "10070010005".
      input = `<div class="itempick">
        <input type="text" class="itempick__show" readonly placeholder="Search for an item…"
          value="${esc(f.display || v)}">
        <input type="hidden" data-f="${esc(f.name)}" value="${esc(v)}">
        <button type="button" class="btn itempick__go">Search</button>
      </div>`;
    } else if (f.type === "check") {
      input = `<input type="checkbox" data-f="${esc(f.name)}"${v ? " checked" : ""}>`;
    } else if (f.type === "text") {
      input = `<textarea data-f="${esc(f.name)}">${esc(v)}</textarea>`;
    } else {
      const t = f.type === "int" || f.type === "float" ? "number" : f.type === "date" ? "date" : "text";
      const step = f.type === "float" ? ' step="any"' : "";
      input = `<input type="${t}"${step} data-f="${esc(f.name)}" value="${esc(v)}">`;
    }
    return `<div class="field">
      <label>${esc(f.label)}${req}</label>${input}
      ${f.help ? `<small>${esc(f.help)}</small>` : ""}
    </div>`;
  }

  /** Fill every link select in a container from its doctype, once. */
  async function hydrateLinks(root) {
    const sels = $$("select[data-link]", root);
    const wanted = Array.from(new Set(sels.map((s) => s.dataset.link)));
    const lists = {};
    await Promise.all(wanted.map(async (dt) => {
      try { lists[dt] = await listDoc(dt, ["name"], [], "name asc"); }
      catch (e) { lists[dt] = []; }
    }));
    sels.forEach((sel) => {
      const rows = lists[sel.dataset.link] || [];
      const cur = sel.dataset.val || "";
      sel.innerHTML = `<option value="">—</option>` + rows.map((r) =>
        `<option value="${esc(r.name)}"${r.name === cur ? " selected" : ""}>${esc(r.name)}</option>`).join("");
      sel.value = cur;
    });
  }

  /** Read a form back out of the DOM. */
  function readForm(root, spec) {
    const out = {};
    spec.fields.forEach((f) => {
      const el = $(`[data-f="${f.name}"]`, root);
      if (!el) return;
      out[f.name] = f.type === "check" ? (el.checked ? 1 : 0)
        : (f.type === "int" || f.type === "float") ? (el.value === "" ? 0 : Number(el.value))
        : el.value;
    });
    (spec.tables || []).forEach((t) => {
      out[t.name] = $$(`tr[data-row="${t.name}"]`, root).map((tr) => {
        const row = {};
        t.fields.forEach((f) => {
          const el = $(`[data-f="${f.name}"]`, tr);
          if (!el) return;
          row[f.name] = f.type === "check" ? (el.checked ? 1 : 0)
            : (f.type === "int" || f.type === "float") ? (el.value === "" ? 0 : Number(el.value))
            : el.value;
        });
        return row;
      });
    });
    return out;
  }

  function tableHtml(t, rows) {
    const head = t.fields.map((f) => `<th>${esc(f.label)}</th>`).join("") + "<th></th>";
    const body = (rows || []).map((r) => rowHtml(t, r)).join("");
    return `<div class="field"><label>${esc(t.label)}</label>
      <table class="gridtbl" data-table="${esc(t.name)}">
        <thead><tr>${head}</tr></thead><tbody>${body}</tbody>
      </table>
      <button class="btn" data-addrow="${esc(t.name)}" style="margin-top:8px">Add row</button></div>`;
  }

  function rowHtml(t, r) {
    r = r || {};
    const cells = t.fields.map((f) => {
      const v = r[f.name] == null ? "" : r[f.name];
      let input;
      if (f.type === "select") {
        input = `<select data-f="${esc(f.name)}">${(f.options || []).map((o) =>
          `<option value="${esc(o)}"${String(o) === String(v) ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
      } else if (f.type === "link") {
        input = `<select data-f="${esc(f.name)}" data-link="${esc(f.doctype)}" data-val="${esc(v)}">
          <option value="${esc(v)}">${esc(v || "—")}</option></select>`;
      } else if (f.type === "check") {
        input = `<input type="checkbox" data-f="${esc(f.name)}"${v ? " checked" : ""}>`;
      } else {
        const ty = (f.type === "int" || f.type === "float") ? "number" : "text";
        const step = f.type === "float" ? ' step="any"' : "";
        input = `<input type="${ty}"${step} data-f="${esc(f.name)}" value="${esc(v)}">`;
      }
      return `<td>${input}</td>`;
    }).join("");
    return `<tr data-row="${esc(t.name)}">${cells}<td><button class="x" data-delrow="1">&times;</button></td></tr>`;
  }

  /** A searchable item picker, by name. Resolves to the chosen row or null. */
  function pickItem(current) {
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.innerHTML = `<input class="searchbox" id="ip-q" placeholder="Type part of the name…" autofocus>
        <div class="queue" id="ip-rows"><div class="skel"></div></div>`;
      let done = false;
      const m = modal({
        title: "Choose an item", sub: "Fertilizer group, this farm's company.",
        body: wrap, foot: [{ label: "Cancel" }],
        onClose: () => { if (!done) resolve(null); },
      });

      let timer;
      async function search(q) {
        const rows = await call("search_fertilizer_items",
          { search: q || null, farm: state.farm || null });
        $("#ip-rows", wrap).innerHTML = rows.map((r) => `
          <div class="qrow" data-pick='${esc(JSON.stringify(r))}' style="cursor:pointer">
            <div class="qrow__mark">${r.item_code === current ? "✓" : ""}</div>
            <div><div class="qrow__name">${esc(r.item_name || r.item_code)}</div>
            <div class="qrow__meta">${esc(r.item_code)} · ${num(r.stock_qty)} ${esc(r.stock_uom || "kg")} in stock</div></div>
            <div class="qrow__right">${r.stock_qty > 0 ? pill("in stock", "good") : pill("empty", "mute")}</div>
          </div>`).join("") || `<div class="none">Nothing matches.</div>`;
      }
      $("#ip-q", wrap).addEventListener("input", (e) => {
        clearTimeout(timer);
        const q = e.target.value;
        timer = setTimeout(() => search(q).catch(() => {}), 250);
      });
      wrap.addEventListener("click", (e) => {
        const row = e.target.closest("[data-pick]");
        if (!row) return;
        done = true;
        resolve(JSON.parse(row.dataset.pick));
        m.close();
      });
      search("").catch(() => {});
    });
  }

  // ---------------------------------------------------------------- what we edit
  /* Curated on purpose. A doctype form shows every field in the schema, in
   * schema order, which is exactly the thing this desk exists to avoid - so
   * each entry names the fields an agronomist actually fills, in the order
   * they think about them. Everything else on the record keeps its default or
   * is set by the controller. */
  const SPECS = {
    programme: {
      doctype: "Fertilizer Programme", title: "Fertilizer Programme",
      icon: "🗂", tint: "rgba(16,185,129,.13)", colour: "#059669",
      sub: "The season's plan. Build it, calculate it, submit it.",
      list: ["name", "season", "farm", "crop", "docstatus"],
      fields: [
        { name: "season", label: "Season", type: "select", reqd: 1,
          options: ["2025/2026", "2026/2027"] },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "production_calendar", label: "Production Calendar", type: "link", doctype: "Production Calendar", reqd: 1 },
        { name: "potassium_source", label: "Potassium Source", type: "itempick",
          help: "Which of the crop's two potassium rules this season uses. Searched by name." },
        { name: "period_type", label: "Programme Period", type: "select", options: ["Full Year", "Custom Period"] },
        { name: "start_month", label: "Start Month", type: "select", showIf: "custom",
          options: ["", "January","February","March","April","May","June","July","August","September","October","November","December"] },
        { name: "end_month", label: "End Month", type: "select", showIf: "custom",
          options: ["", "January","February","March","April","May","June","July","August","September","October","November","December"] },
      ],
    },
    farm: {
      doctype: "CNP Farm", title: "Farm", icon: "🌍", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "The farms this module plans for.",
      list: ["name", "kaitet_farm_code", "default_crop", "is_active"],
      fields: [
        { name: "farm_name", label: "Farm Name", reqd: 1 },
        { name: "kaitet_farm_code", label: "Farm Code" },
        { name: "default_crop", label: "Default Crop", type: "link", doctype: "Crop" },
        { name: "farm_manager", label: "Farm Manager", type: "link", doctype: "User" },
        { name: "warehouse", label: "Warehouse", type: "link", doctype: "Warehouse" },
        { name: "is_active", label: "Active", type: "check" },
      ],
    },
    section: {
      doctype: "Section", title: "Section", icon: "🗺", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Blocks are grouped into sections; the engine calculates per section.",
      list: ["name", "farm", "is_active"],
      fields: [
        { name: "section_name", label: "Section Name", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "is_active", label: "Active", type: "check" },
      ],
    },
    block: {
      doctype: "Farm Block", title: "Farm Block", icon: "🧱", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Area, trees and last year's yield - what the whole calculation rests on.",
      list: ["name", "section", "area_ha", "tree_count", "previous_year_yield_kg_ha"],
      fields: [
        { name: "block_name", label: "Block Name", reqd: 1 },
        { name: "block_number", label: "Block Number" },
        { name: "section", label: "Section", type: "link", doctype: "Section", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop" },
        { name: "area_ha", label: "Area (Ha)", type: "float", reqd: 1 },
        { name: "tree_count", label: "Tree Count", type: "int", reqd: 1 },
        { name: "previous_year_yield_kg_ha", label: "Last Year Yield (Kg/Ha)", type: "float",
          help: "Decides the block's yield tier." },
        { name: "planting_year", label: "Planting Year", type: "int" },
      ],
    },
    crop: {
      doctype: "Crop", title: "Crop", icon: "🌱", tint: "rgba(16,185,129,.13)", colour: "#059669",
      sub: "Yield tiers and nutrient rules - the engine's master data.",
      list: ["name", "item", "compost_dose_kg"],
      fields: [
        { name: "crop_name", label: "Crop Name", reqd: 1 },
        { name: "item", label: "Produce Item", type: "link", doctype: "Item",
          help: "The harvested produce, not a fertilizer." },
        { name: "compost_dose_kg", label: "Compost Dose (Kg)", type: "float" },
        { name: "compost_n_pct", label: "Compost N (%)", type: "float" },
        { name: "leaf_adjustment_pct", label: "Leaf Adjustment (%)", type: "float" },
      ],
      tables: [
        { name: "yield_tiers", label: "Yield Tiers", fields: [
          { name: "tier_label", label: "Tier" },
          { name: "tier_tonnage", label: "Tonnage", type: "float" },
          { name: "min_yield_kg_ha", label: "Min Kg/Ha", type: "float" },
          { name: "max_yield_kg_ha", label: "Max Kg/Ha", type: "float" },
          { name: "sort_order", label: "Order", type: "int" },
        ] },
        { name: "nutrient_rules", label: "Nutrient Rules", fields: [
          { name: "product", label: "Product", type: "link", doctype: "Fertilizer Product" },
          { name: "fertilizer_product", label: "Fallback Item", type: "link", doctype: "Item" },
          { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
          { name: "rate_per_tonne", label: "Rate/Tonne", type: "float" },
          { name: "bag_weight_kg", label: "Bag Kg", type: "float" },
          { name: "product_nutrient_pct", label: "Nutrient %", type: "float" },
          { name: "apply_compost_netting", label: "Net Compost", type: "check" },
          { name: "nutrient_source_group", label: "Source Group" },
        ] },
      ],
    },
    product: {
      doctype: "Fertilizer Product", title: "Fertilizer Product", icon: "🧪",
      tint: "rgba(245,158,11,.13)", colour: "#d97706",
      sub: "CAN, MOP, K2SO4 — and the spellings each is known by on this site.",
      list: ["name", "product_name", "nutrient", "disabled"],
      fields: [
        { name: "product_code", label: "Product Code", reqd: 1, help: "e.g. CAN" },
        { name: "product_name", label: "Product Name" },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
        { name: "item_group", label: "Item Group", type: "link", doctype: "Item Group" },
        { name: "search_terms", label: "Search Terms", type: "text", reqd: 1,
          help: "One per line. List every spelling - POTASIUM and POTASSIUM are different items here." },
        { name: "exclude_terms", label: "Exclude Terms", type: "text" },
        { name: "disabled", label: "Disabled", type: "check" },
      ],
    },
    calendar: {
      doctype: "Production Calendar", title: "Production Calendar", icon: "🗓",
      tint: "rgba(79,70,229,.13)", colour: "#4f46e5",
      sub: "Which months each product is applied in, and in what share.",
      list: ["name", "season", "farm"],
      fields: [
        { name: "season", label: "Season", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "season_notes", label: "Notes", type: "text" },
      ],
      tables: [
        { name: "fertilizer_schedule", label: "Fertilizer Schedule", fields: [
          { name: "fertilizer_product", label: "Item", type: "link", doctype: "Item" },
          { name: "application_month", label: "Month", type: "select", options: ["January","February","March","April","May","June","July","August","September","October","November","December"] },
          { name: "percentage", label: "%", type: "float" },
        ] },
      ],
    },
    leaf: {
      doctype: "Leaf Analysis", title: "Leaf Analysis", icon: "🍃",
      tint: "rgba(34,197,94,.13)", colour: "#16a34a",
      sub: "Lab results per section, which adjust the calculated rates.",
      list: ["name", "section", "sampling_date", "yield_tier"],
      fields: [
        { name: "section", label: "Section", type: "link", doctype: "Section", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm" },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop" },
        { name: "block", label: "Block", type: "link", doctype: "Farm Block" },
        { name: "sampling_date", label: "Sampling Date", type: "date" },
        { name: "season", label: "Season" },
      ],
      tables: [
        { name: "nutrient_results", label: "Nutrient Results", fields: [
          { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
          { name: "result_value", label: "Result", type: "float" },
          { name: "unit", label: "Unit", type: "select", options: ["%", "ppm"] },
        ] },
      ],
    },
    norm: {
      doctype: "Leaf Analysis Norm", title: "Leaf Analysis Norm", icon: "📏",
      tint: "rgba(6,182,212,.13)", colour: "#0891b2",
      sub: "The healthy range per nutrient. A result outside it moves the rate.",
      list: ["name", "crop", "nutrient", "low", "high", "midpoint"],
      fields: [
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"], reqd: 1 },
        { name: "low", label: "Low", type: "float" },
        { name: "high", label: "High", type: "float" },
        { name: "midpoint", label: "Midpoint", type: "float" },
        { name: "unit", label: "Unit", type: "select", options: ["%", "ppm"] },
      ],
    },
    settings: {
      doctype: "Crop Nutrition Planning Settings", single: true,
      title: "Module Settings", icon: "⚙", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Module-wide defaults.",
      fields: [
        { name: "upcoming_alert_days", label: "Alert Days Before Application", type: "int" },
        { name: "variance_threshold_pct", label: "Variance Alert Threshold (%)", type: "int" },
        { name: "require_programme_approval", label: "Require Programme Approval", type: "check",
          help: "Off: you submit the programme and it takes effect. On: it goes to the consultant, then the farm manager." },
      ],
    },
  };

  // --------------------------------------------------------------- record popups
  /** Open one record for editing, or a blank one. */
  async function openRecord(key, name, afterSave) {
    const spec = SPECS[key];
    let data = {};
    if (spec.single) {
      data = await getDoc(spec.doctype, spec.doctype);
    } else if (name) {
      data = await getDoc(spec.doctype, name);
    }

    const form = document.createElement("div");
    form.innerHTML = `<div class="fgrid">${spec.fields.map((f) =>
      fieldHtml(f, data[f.name])).join("")}</div>` +
      (spec.tables || []).map((t) => tableHtml(t, data[t.name])).join("");

    const m = modal({
      title: name || spec.single ? `Edit ${spec.title}` : `New ${spec.title}`,
      sub: spec.sub, body: form, size: (spec.tables || []).length ? "wide" : "",
      foot: [
        { label: "Cancel" },
        { label: "Save", cls: "btn--ink", onClick: async (h) => {
            const values = readForm(form, spec);
            const payload = spec.single
              ? Object.assign({}, data, values, { doctype: spec.doctype, name: spec.doctype })
              : name
                ? Object.assign({}, data, values)
                : Object.assign({ doctype: spec.doctype }, values);
            const saved = await saveDoc(payload);
            toast(`${spec.title} saved.`, "good");
            h.close();
            if (afterSave) afterSave(saved);
          } },
      ],
    });

    // Full Year is the default and the months are noise until someone asks for
    // a window, so they are only shown when Custom Period is chosen.
    const period = $('[data-f="period_type"]', form);
    if (period) {
      const sync = () => {
        const custom = period.value === "Custom Period";
        spec.fields.filter((f) => f.showIf === "custom").forEach((f) => {
          const el = $(`[data-f="${f.name}"]`, form);
          if (el) el.closest(".field").style.display = custom ? "" : "none";
        });
      };
      period.addEventListener("change", sync);
      sync();
    }

    // searching for an item by name, from inside the form
    form.addEventListener("click", async (e) => {
      const go = e.target.closest(".itempick__go");
      if (!go) return;
      const wrap = go.closest(".itempick");
      const hidden = $('input[type="hidden"]', wrap);
      const shown = $(".itempick__show", wrap);
      const picked = await pickItem(hidden.value);
      if (picked) { hidden.value = picked.item_code; shown.value = picked.item_name || picked.item_code; }
    });

    // rows can be added and removed while the popup is open
    form.addEventListener("click", (e) => {
      const add = e.target.closest("[data-addrow]");
      if (add) {
        const t = (spec.tables || []).find((x) => x.name === add.dataset.addrow);
        const tb = $(`table[data-table="${t.name}"] tbody`, form);
        tb.insertAdjacentHTML("beforeend", rowHtml(t, {}));
        hydrateLinks(tb);
        return;
      }
      const del = e.target.closest("[data-delrow]");
      if (del) del.closest("tr").remove();
    });

    await hydrateLinks(form);
    return m;
  }

  /** A list of a doctype's records, each opening the editor. */
  async function openList(key) {
    const spec = SPECS[key];
    if (spec.single) return openRecord(key);

    const wrap = document.createElement("div");
    wrap.innerHTML = `<div class="queue"><div class="skel"></div></div>`;
    const m = modal({
      title: spec.title, sub: spec.sub, body: wrap, size: "wide",
      foot: [{ label: "Close" },
             { label: `New ${spec.title}`, cls: "btn--ink",
               onClick: (h) => { h.close(); openRecord(key, null, () => openList(key)); } }],
    });

    async function draw() {
      const rows = await listDoc(spec.doctype, spec.list);
      $(".queue", wrap).innerHTML = rows.map((r) => {
        const extra = spec.list.slice(1).map((f) =>
          r[f] === undefined || r[f] === null || r[f] === "" ? null : `${f.replace(/_/g, " ")}: ${r[f]}`)
          .filter(Boolean).join(" · ");
        return `<div class="qrow" data-open="${esc(r.name)}" style="cursor:pointer">
          <div class="qrow__mark">${esc(String(r.name).slice(0, 2))}</div>
          <div><div class="qrow__name">${esc(r.name)}</div>
          <div class="qrow__meta">${esc(extra)}</div></div>
          <div class="qrow__right"><span class="btn">Edit</span></div>
        </div>`;
      }).join("") || `<div class="none">Nothing yet. Use “New ${esc(spec.title)}”.</div>`;
    }
    wrap.addEventListener("click", (e) => {
      const row = e.target.closest("[data-open]");
      if (row) { m.close(); openRecord(key, row.dataset.open, () => openList(key)); }
    });
    await draw();
    return m;
  }

  // ------------------------------------------------------------------- rendering
  function kpi(label, value, cls, unit) {
    return `<div class="kpi">
      <div class="kpi__label">${esc(label)}</div>
      <div class="kpi__value${cls ? " " + cls : ""}">${esc(value)}</div>
      ${unit ? `<div class="kpi__unit">${esc(unit)}</div>` : ""}
    </div>`;
  }

  function pill(text, kind) {
    return `<span class="pill${kind ? " pill--" + kind : ""}">${esc(text)}</span>`;
  }

  /** What the programme is, in the words the agronomist uses. With approval
   *  switched off there are two states that matter: still being built, or in
   *  force. The workflow states only appear if someone turns approval on. */
  function progState(p) {
    if (p.docstatus === 1) return p.workflow_state === "Approved" || !p.workflow_state
      ? "Submitted" : p.workflow_state;
    if (p.docstatus === 2) return "Cancelled";
    return p.workflow_state && p.workflow_state !== "Draft" ? p.workflow_state : "Draft";
  }

  function stateKind(s) {
    if (s === "Submitted" || s === "Approved") return "good";
    if (s === "Rejected" || s === "Cancelled") return "bad";
    if (s === "Draft") return "mute";
    return "warn";
  }

  function renderKpis(d) {
    const m = d.metrics || {};
    const c = d.current;
    $("#kpis").innerHTML = [
      kpi("Programme state", c ? (c.workflow_state || "Draft") : "none",
          c ? stateKind(c.workflow_state) === "good" ? "good" : "" : ""),
      kpi("Blocks planned", num(m.total_plans), "", "rounds across the season"),
      kpi("Season progress", num(m.progress_pct) + "%", "info",
          `${num(m.applied)} of ${num(m.total_plans)} applied`),
      kpi("Pending applications", num(m.pending_applications), "warn"),
      kpi("Ready to record", num(m.ready_to_record), "good", "issued by the store"),
      kpi("Pending store requests", num(m.pending_requests), "warn"),
    ].join("");
  }

  function renderProgramme(d) {
    const c = d.current;
    if (!c) {
      $("#prog-meta").textContent = "";
      $("#prog-body").innerHTML = `<div class="none">No programme for this farm yet.
        Create one in the UpandeCNP workspace, then it appears here.</div>`;
      $("#prod-body").innerHTML = `<div class="none">—</div>`;
      return;
    }
    const a = c.actions || {};
    $("#prog-meta").innerHTML = `${esc(c.season)} · ${esc(c.crop || "")}`;

    const steps = (a.steps || []).map((s) => `
      <div class="step">
        <div class="step__tick${s.done ? " on" : ""}">${s.done ? "✓" : ""}</div>
        <div>
          <div class="step__label">${esc(s.label)}</div>
          <div class="step__detail">${esc(s.detail || "")}</div>
        </div>
      </div>`).join("");

    const period = c.period_type === "Custom Period"
      ? `${esc(c.start_month)} – ${esc(c.end_month)}`
      : "Full year";

    $("#prog-body").innerHTML = `
      <div class="qrow" style="border:0;padding-left:0">
        <div class="qrow__mark">${esc((c.season || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(c.name)}</div>
          <div class="qrow__meta">${period} · ${num(c.blocks)} blocks · ${num(c.lines)} lines</div>
        </div>
        <div class="qrow__right">${pill(progState(c), stateKind(progState(c)))}</div>
      </div>
      <div class="steps">${steps}</div>
      ${a.blocked ? `<div class="none">${esc(a.blocked)}</div>` : ""}
      <div class="btnrow">
        <button class="btn" data-edit-prog="${esc(c.name)}">Edit details</button>
        <button class="btn" data-act="pull_blocks" ${a.editable ? "" : "disabled"}>Pull blocks</button>
        <button class="btn" data-act="load_products" ${a.editable ? "" : "disabled"}>Load products</button>
        <button class="btn" data-act="calculate" ${a.editable ? "" : "disabled"}>Run calculation</button>
        <button class="btn btn--ink" data-act="submit"
          ${a.editable && a.ready_to_send ? "" : "disabled"}>Submit programme</button>
      </div>`;

    // products, each with the item it draws from and whether stock covers it
    const rows = (c.products || []).map((p) => {
      const short = p.shortfall > 0;
      return `<div class="qrow">
        <div class="qrow__mark">${esc(p.product.slice(0, 3))}</div>
        <div>
          <div class="qrow__name">${esc(p.item_name || p.item || "No item chosen")}</div>
          <div class="qrow__meta">${esc(p.product)}${p.item ? " · " + esc(p.item) : ""} ·
            needs ${num(p.required)} kg, ${num(p.available)} kg in stock</div>
        </div>
        <div class="qrow__right">
          ${short ? pill("short " + num(p.shortfall) + " kg", "bad")
                  : p.item ? pill("covered", "good") : pill("choose an item", "warn")}
          <button class="btn" data-choose="${esc(p.product)}"
            ${c.actions && c.actions.editable ? "" : "disabled"}>Change</button>
        </div>
      </div>`;
    }).join("");
    $("#prod-meta").textContent = (c.products || []).length + " products";
    $("#prod-body").innerHTML = rows
      || `<div class="none">No products loaded. Use “Load products” to list what this crop needs.</div>`;
  }

  function renderProgrammeList(d) {
    $("#prog-list").innerHTML = (d.programmes || []).map((p) => `
      <div class="qrow">
        <div class="qrow__mark">${esc((p.season || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(p.name)}</div>
          <div class="qrow__meta">${esc(p.season)} · ${esc(p.farm || "")} ·
            ${p.period_type === "Custom Period"
              ? esc(p.start_month) + " – " + esc(p.end_month) : "Full year"}</div>
        </div>
        <div class="qrow__right">${pill(progState(p), stateKind(progState(p)))}</div>
      </div>`).join("") || `<div class="none">Nothing yet.</div>`;
  }

  // ----------------------------------------------------------------- other tabs
  function bar(pct, kind) {
    const w = Math.max(0, Math.min(100, Number(pct) || 0));
    return `<div class="bar"><div class="bar__fill${kind ? " " + kind : ""}" style="width:${w}%"></div></div>`;
  }
  const stateKindFor = (st) =>
    st === "Completed" ? "good" : st === "In progress" ? "warn"
    : st === "No plan" ? "mute" : "info";

  let allBlocks = [];

  async function loadPlans() {
    // every block, searchable
    try {
      allBlocks = await call("get_desk_blocks",
        { farm: state.farm || null, season: state.season || null });
      drawBlocks();
    } catch (e) { $("#blocks").innerHTML = `<div class="none">Could not load blocks.</div>`; }

    // and the ones with work outstanding
    try {
      const rows = await call("get_plan_queue",
        { farm: state.farm || null, season: state.season || null });
      $("#plans-meta").textContent = rows.length + " blocks";
      $("#plans").innerHTML = rows.map((r) => `
        <div class="qrow" data-block="${esc(r.block)}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.block)}</div>
            <div class="qrow__meta">${esc(r.section || "")} · ${num(r.rounds)} rounds ·
              ${num(r.total_kg, 0)} kg · next ${esc(r.next_month || "—")}</div>
          </div>
          <div class="qrow__right">${r.issued
            ? pill(num(r.issued) + " issued", "good") : pill("awaiting store", "warn")}</div>
        </div>`).join("") || `<div class="none">No block has work outstanding.</div>`;
    } catch (e) { $("#plans").innerHTML = `<div class="none">Could not load.</div>`; }
  }

  function drawBlocks() {
    const q = ($("#block-search").value || "").toLowerCase();
    const rows = allBlocks.filter((b) =>
      !q || (b.block || "").toLowerCase().includes(q) || (b.section || "").toLowerCase().includes(q));
    $("#blocks-meta").textContent = `${rows.length} of ${allBlocks.length}`;
    $("#blocks").innerHTML = rows.map((b) => `
      <div class="qrow" data-block="${esc(b.block)}" style="cursor:pointer">
        <div class="qrow__mark">${esc((b.block || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(b.block)}</div>
          <div class="qrow__meta">${esc(b.section || "")} · ${num(b.area_ha, 2)} ha ·
            ${num(b.tree_count)} trees · ${num(b.done)}/${num(b.rounds)} rounds</div>
        </div>
        <div class="qrow__right">${bar(b.pct, b.pct >= 100 ? "good" : b.pct ? "warn" : "")}
          ${pill(b.state, stateKindFor(b.state))}</div>
      </div>`).join("") || `<div class="none">No block matches.</div>`;
  }

  /** One block, opened from either list. */
  async function openBlock(block) {
    let d;
    try { d = await call("get_block_detail", { block, season: state.season || null }); }
    catch (e) { return; }
    const i = d.info, y = d.yield;
    const vsAvg = Number(y.vs_avg_pct) || 0;
    const body = `
      <div class="statline"><span class="statline__k">Section</span>
        <span class="statline__v">${esc(i.section || "—")}</span></div>
      <div class="statline"><span class="statline__k">Area · trees</span>
        <span class="statline__v">${num(i.area_ha, 2)} ha · ${num(i.tree_count)}</span></div>
      <div class="statline"><span class="statline__k">Rounds done</span>
        <span class="statline__v">${num(d.done)} of ${num(d.rounds)}</span></div>
      ${bar(d.pct, d.pct >= 100 ? "good" : d.pct ? "warn" : "")}
      <div class="statline" style="margin-top:14px"><span class="statline__k">Planned · applied</span>
        <span class="statline__v">${num(d.planned_kg)} · ${num(d.actual_kg)} kg</span></div>

      <div class="card__head" style="margin:22px 0 10px"><h3>Last year's yield</h3></div>
      <div class="statline"><span class="statline__k">This block</span>
        <span class="statline__v">${num(y.block)} kg/ha</span></div>
      ${bar(y.farm_best ? (y.block / y.farm_best) * 100 : 0,
            vsAvg >= 0 ? "good" : "warn")}
      <div class="statline"><span class="statline__k">Farm average · best</span>
        <span class="statline__v">${num(y.farm_avg)} · ${num(y.farm_best)} kg/ha</span></div>
      <div class="none" style="text-align:left;padding:10px 0">
        ${vsAvg >= 0 ? "Above" : "Below"} the farm average by ${num(Math.abs(vsAvg))}% —
        which is what put this block in its yield tier, and so what set these rates.
      </div>

      <div class="card__head" style="margin:18px 0 10px"><h3>Rounds</h3></div>
      <div class="queue queue--5">${d.plans.map((p) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((p.application_month || "?").slice(0, 3))}</div>
          <div><div class="qrow__name">${esc(p.fertilizer_product_name || p.fertilizer_product)}</div>
          <div class="qrow__meta">${esc(p.application_month)}${p.application_year ? " " + p.application_year : ""} ·
            ${num(p.total_kg_required)} kg · ${num(p.dose_per_tree_g, 1)} g/tree
            ${p.times_pushed ? " · pushed " + p.times_pushed + "×" : ""}</div></div>
          <div class="qrow__right">${pill(p.status,
            p.status === "Applied" || p.status === "Verified" ? "good"
            : p.status === "Issued" ? "warn" : "mute")}</div>
        </div>`).join("") || `<div class="none">No rounds planned.</div>`}</div>`;
    modal({ title: block, sub: `${i.farm || ""} · ${i.crop || ""}`, body, size: "wide",
            foot: [{ label: "Close" }] });
  }

  async function loadRequests() {
    const el = $("#requests");
    try {
      const rows = await call("get_desk_store_requests", { farm: state.farm || null });
      state.requests = rows;
      $("#req-meta").textContent = rows.length + " requests";
      el.innerHTML = rows.map((r, idx) => `
        <div class="qrow" data-req="${idx}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.item_code_name || r.item_code || r.name)}</div>
            <div class="qrow__meta">${esc(r.block || "—")} · ${num(r.qty)} kg ·
              ${esc(r.employee_name || "unknown supervisor")} · ${esc(r.transaction_date || "")}</div>
          </div>
          <div class="qrow__right">${pill(r.state || "—",
            r.state === "Approved" || r.state === "Issued" ? "good"
            : r.state === "Rejected" || r.state === "Cancelled" ? "bad" : "warn")}</div>
        </div>`).join("") || `<div class="none">No supervisor has raised a request yet.</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load requests.</div>`; }
  }

  function openRequest(idx) {
    const r = (state.requests || [])[idx];
    if (!r) return;
    const body = `
      <div class="statline"><span class="statline__k">Supervisor</span>
        <span class="statline__v">${esc(r.employee_name || r.employee || "—")}</span></div>
      <div class="statline"><span class="statline__k">Amount requested</span>
        <span class="statline__v">${num(r.qty)} kg</span></div>
      <div class="statline"><span class="statline__k">Product</span>
        <span class="statline__v">${esc(r.item_code_name || r.item_code || "—")}</span></div>
      <div class="statline"><span class="statline__k">Block</span>
        <span class="statline__v">${esc(r.block || "—")}</span></div>
      <div class="statline"><span class="statline__k">Section</span>
        <span class="statline__v">${esc(r.section || "—")}</span></div>
      <div class="statline"><span class="statline__k">For the month of</span>
        <span class="statline__v">${esc(r.application_month || "—")}</span></div>
      <div class="statline"><span class="statline__k">Raised on</span>
        <span class="statline__v">${esc(r.transaction_date || "—")}</span></div>
      <div class="statline"><span class="statline__k">Status</span>
        <span class="statline__v">${esc(r.state || r.status || "—")}</span></div>
      <div class="none" style="text-align:left">Request ${esc(r.name)}${
        r.plan ? ` · plan ${esc(r.plan)}` : ""}</div>`;
    modal({ title: "Store request", sub: r.block || "", body, foot: [{ label: "Close" }] });
  }

  async function loadApplications() {
    try {
      const rows = await call("get_desk_applications",
        { farm: state.farm || null, season: state.season || null });
      state.apps = rows;
      $("#apps-meta").textContent = `${rows.length} recorded`;
      $("#apps").innerHTML = rows.map((r, idx) => `
        <div class="qrow" data-app="${idx}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.fertilizer_product_name || r.fertilizer_product)}</div>
            <div class="qrow__meta">${esc(r.block)} · ${num(r.actual_quantity_applied_kg, 1)} kg ·
              ${esc(r.application_date || "")} · ${esc(r.supervisor_name || "")}</div>
          </div>
          <div class="qrow__right">${r.applied_in_full ? pill("in full", "good") : pill("partial", "warn")}</div>
        </div>`).join("") || `<div class="none">Nothing recorded yet.</div>`;
    } catch (e) { $("#apps").innerHTML = `<div class="none">Could not load applications.</div>`; }

    // planned against applied, per section
    try {
      const rows = await call("get_variance_by_section",
        { farm: state.farm || null, season: state.season || null });
      $("#variance").innerHTML = rows.map((r) => `
        <div class="hb" data-section="${esc(r.section)}" style="cursor:pointer">
          <div class="hb__name">${esc(r.section || "—")}</div>
          <div class="hb__lane">
            <div class="hb__est"></div>
            <div class="hb__act${r.pct >= 100 ? "" : " bad"}"
              style="width:${Math.max(0, Math.min(100, r.pct))}%"></div>
          </div>
          <div class="hb__pct">${num(r.actual)} / ${num(r.planned)} kg</div>
        </div>`).join("") || `<div class="none">Nothing planned yet.</div>`;
    } catch (e) { $("#variance").innerHTML = `<div class="none">Could not load.</div>`; }
  }

  function openApplication(idx) {
    const a = (state.apps || [])[idx];
    if (!a) return;
    const body = `
      <div class="statline"><span class="statline__k">Block</span>
        <span class="statline__v">${esc(a.block)}</span></div>
      <div class="statline"><span class="statline__k">Product</span>
        <span class="statline__v">${esc(a.fertilizer_product_name || a.fertilizer_product)}</span></div>
      <div class="statline"><span class="statline__k">Date</span>
        <span class="statline__v">${esc(a.application_date || "—")}</span></div>
      <div class="statline"><span class="statline__k">Planned · applied</span>
        <span class="statline__v">${num(a.planned_quantity_kg, 1)} · ${num(a.actual_quantity_applied_kg, 1)} kg</span></div>
      <div class="statline"><span class="statline__k">Variance</span>
        <span class="statline__v">${num(a.variance_kg, 1)} kg</span></div>
      ${a.applied_in_full ? "" : `<div class="none" style="text-align:left">
        Partial — ${esc(a.partial_reason || "no reason given")}</div>`}
      <div class="statline"><span class="statline__k">Method · weather</span>
        <span class="statline__v">${esc(a.application_method || "—")} · ${esc(a.weather_conditions || "—")}</span></div>
      <div class="statline"><span class="statline__k">Supervisor</span>
        <span class="statline__v">${esc(a.supervisor_name || a.supervisor || "—")}</span></div>
      <div class="statline"><span class="statline__k">Applicators</span>
        <span class="statline__v">${esc((a.applicators || []).join(", ") || "—")}</span></div>
      <div class="none" style="text-align:left">${esc(a.name)}${
        a.material_request ? ` · request ${esc(a.material_request)}` : ""}</div>`;
    modal({ title: "Application", sub: a.block, body, foot: [{ label: "Close" }] });
  }

  async function openSectionVariance(section) {
    let rows;
    try {
      rows = await call("get_variance_by_block",
        { section, farm: state.farm || null, season: state.season || null });
    } catch (e) { return; }
    const body = rows.map((r) => `
      <div class="hb">
        <div class="hb__name">${esc(r.block)}</div>
        <div class="hb__lane">
          <div class="hb__est"></div>
          <div class="hb__act${r.pct >= 100 ? "" : " bad"}"
            style="width:${Math.max(0, Math.min(100, r.pct))}%"></div>
        </div>
        <div class="hb__pct">${num(r.actual)} / ${num(r.planned)} kg</div>
      </div>`).join("") || `<div class="none">Nothing planned in this section.</div>`;
    modal({ title: section, sub: "Planned against applied, per block",
            body, size: "wide", foot: [{ label: "Close" }] });
  }

  async function loadStock() {
    const el = $("#stock");
    try {
      const rows = await call("get_desk_stock",
        { farm: state.farm || null, season: state.season || null });
      const inProg = rows.filter((r) => r.in_programme);
      const rest = rows.filter((r) => !r.in_programme);
      const line = (r) => `
        <div class="qrow">
          <div class="qrow__mark">${r.sufficient ? "✓" : "!"}</div>
          <div>
            <div class="qrow__name">${esc(r.item_name || r.item_code)}</div>
            <div class="qrow__meta">${esc(r.item_code)} · ${num(r.stock)} ${esc(r.uom || "kg")} in store${
              r.in_programme ? ` · ${num(r.required)} needed` : ""}</div>
          </div>
          <div class="qrow__right">${r.in_programme
            ? (r.sufficient ? pill("covers it", "good")
                            : pill("short " + num(r.shortfall) + " kg", "bad"))
            : pill("not in the programme", "mute")}</div>
        </div>`;
      el.innerHTML =
        `<div class="card__head"><h3>Needed by this programme</h3>
           <span class="meta">${inProg.length} items</span></div>
         <div class="queue">${inProg.map(line).join("") || `<div class="none">Nothing required yet — calculate the programme first.</div>`}</div>
         <div class="card__head" style="margin-top:22px"><h3>Also in the store</h3>
           <span class="meta">${rest.length} items</span></div>
         <div class="queue queue--5">${rest.map(line).join("") || `<div class="none">—</div>`}</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load stock.</div>`; }
  }

  // --------------------------------------------------------------------- actions
  async function act(button) {
    const kind = button.dataset.act;
    const c = state.data && state.data.current;
    if (!c) return;
    const label = button.textContent;
    button.disabled = true; button.textContent = "Working…";
    try {
      if (kind === "pull_blocks") {
        const r = await call("desk_pull_blocks", { programme: c.name });
        toast(`${r.blocks} blocks pulled.`, "good");
      } else if (kind === "load_products") {
        const r = await call("load_programme_products", { programme: c.name });
        toast(`${(r.products || []).length} products listed. Choose an item for each.`, "good");
      } else if (kind === "calculate") {
        const r = await call("desk_calculate", { programme: c.name });
        toast(`${r.lines} programme lines generated.`, "good");
      } else if (kind === "submit") {
        const r = await call("desk_submit_programme", { programme: c.name });
        toast(r.already ? "Already submitted." :
          "Programme submitted — the block plans are created.", "good");
      }
      await load();
    } catch (e) {
      if (!e.handled) toast(e.message, "bad");
      button.disabled = false; button.textContent = label;
    }
  }

  /** Choosing the item a product is drawn from, with stock and the rule in view. */
  async function chooseItem(product) {
    const c = state.data && state.data.current;
    if (!c) return;
    let choices;
    try { choices = await call("get_product_choices", { programme: c.name, product }); }
    catch (e) { return; }

    const opts = choices.options || [];
    if (!opts.length) {
      toast(`No item matches the search terms on ${product}.`, "bad");
      return;
    }
    const r = choices.rule;
    const rule = r
      ? `<div class="none" style="text-align:left;background:var(--surface);border-radius:14px;padding:14px">
           <b>The nutrient rule is the same whichever you pick</b><br>
           ${esc(r.nutrient || "-")} · ${num(r.rate_per_tonne)} per tonne ·
           ${num(r.bag_weight_kg)} kg bag · ${num(r.product_nutrient_pct)}% content
           ${r.apply_compost_netting ? " · compost netted" : ""}
         </div>`
      : "";
    const rows = opts.map((o) => `
      <div class="qrow" data-pick="${esc(o.item_code)}" style="cursor:pointer">
        <div class="qrow__mark">${o.item_code === choices.current ? "✓" : ""}</div>
        <div><div class="qrow__name">${esc(o.item_name || o.item_code)}</div>
        <div class="qrow__meta">${esc(o.item_code)} · ${num(o.stock_qty)} ${esc(o.stock_uom || "kg")} in stock</div></div>
        <div class="qrow__right">${o.stock_qty > 0 ? pill("in stock", "good") : pill("empty", "bad")}</div>
      </div>`).join("");

    const wrap = document.createElement("div");
    wrap.innerHTML = rule + `<div class="queue" style="margin-top:12px">${rows}</div>`;
    const m = modal({
      title: `Which item for ${product}?`,
      sub: "Tap the one this season should be drawn from.",
      body: wrap, foot: [{ label: "Cancel" }],
    });
    wrap.addEventListener("click", async (e) => {
      const row = e.target.closest("[data-pick]");
      if (!row) return;
      try {
        await call("set_product_item",
          { programme: c.name, product, item: row.dataset.pick });
        toast(`${product} will be drawn from ${row.dataset.pick}.`, "good");
        m.close();
        await load();
      } catch (err) { /* already surfaced */ }
    });
  }

  // ------------------------------------------------------------------ bootstrap
  function tabs() {
    $$(".tab").forEach((t) => t.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("on", x === t));
      $$(".tabpanel").forEach((p) => p.classList.toggle("on", p.id === "tab-" + t.dataset.tab));
      const which = t.dataset.tab;
      if (which === "plans") loadPlans();
      if (which === "requests") loadRequests();
      if (which === "applications") loadApplications();
      if (which === "stock") loadStock();
      if (which === "setup") renderSetup();
    }));
  }

  function fillSelect(el, values, current) {
    el.innerHTML = values.map((v) =>
      `<option value="${esc(v)}"${v === current ? " selected" : ""}>${esc(v)}</option>`).join("");
  }

  async function load() {
    const d = await call("get_agronomist_desk",
      { farm: state.farm || null, season: state.season || null });
    state.data = d;
    if (!$("#farm").options.length) {
      fillSelect($("#farm"), d.farms && d.farms.length ? d.farms : ["All Farms"], d.farm);
      fillSelect($("#season"), d.seasons || ["All Seasons"], state.season);
    }
    renderKpis(d);
    renderProgramme(d);
    renderProgrammeList(d);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const u = cfg.user || "";
    $("#avatar").textContent = (u.slice(0, 2) || "--").toUpperCase();
    tabs();
    $("#refresh").addEventListener("click", () => load());
    $("#block-search").addEventListener("input", () => drawBlocks());
    $("#farm").addEventListener("change", (e) => { state.farm = e.target.value; load(); });
    $("#season").addEventListener("change", (e) => { state.season = e.target.value; load(); });

    // One listener for the whole page: the buttons are re-rendered constantly,
    // so binding them individually would leak handlers on every refresh.
    document.addEventListener("click", (e) => {
      const a = e.target.closest("[data-act]");
      if (a) return act(a);
      const ch = e.target.closest("[data-choose]");
      if (ch) return chooseItem(ch.dataset.choose);
      const lst = e.target.closest("[data-open-list]");
      if (lst) return openList(lst.dataset.openList).catch(() => {});
      const nw = e.target.closest("[data-new]");
      if (nw) return openRecord(nw.dataset.new, null, () => load()).catch(() => {});
      const ed = e.target.closest("[data-edit-prog]");
      if (ed) return openRecord("programme", ed.dataset.editProg, () => load()).catch(() => {});
      const bl = e.target.closest("[data-block]");
      if (bl) return openBlock(bl.dataset.block);
      const rq = e.target.closest("[data-req]");
      if (rq) return openRequest(Number(rq.dataset.req));
      const ap = e.target.closest("[data-app]");
      if (ap) return openApplication(Number(ap.dataset.app));
      const sv = e.target.closest("[data-section]");
      if (sv) return openSectionVariance(sv.dataset.section);
    });

    load().catch(() => {});
  });
})();
