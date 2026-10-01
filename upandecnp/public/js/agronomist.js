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

  /** Workflow state to a colour, so the state reads before it is read. */
  function stateKind(s) {
    if (s === "Approved") return "good";
    if (s === "Rejected") return "bad";
    if (s === "Draft" || !s) return "mute";
    return "warn";   // the pending states
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
        <div class="qrow__right">${pill(c.workflow_state || "Draft", stateKind(c.workflow_state))}</div>
      </div>
      <div class="steps">${steps}</div>
      ${a.blocked ? `<div class="none">${esc(a.blocked)}</div>` : ""}
      <div class="btnrow">
        <button class="btn" data-act="pull_blocks" ${a.editable ? "" : "disabled"}>Pull blocks</button>
        <button class="btn" data-act="load_products" ${a.editable ? "" : "disabled"}>Load products</button>
        <button class="btn" data-act="calculate" ${a.editable ? "" : "disabled"}>Run calculation</button>
        <button class="btn btn--ink" data-act="send"
          ${a.editable && a.ready_to_send ? "" : "disabled"}>Send for review</button>
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
        <div class="qrow__right">${pill(p.workflow_state || "Draft", stateKind(p.workflow_state))}</div>
      </div>`).join("") || `<div class="none">Nothing yet.</div>`;
  }

  // ----------------------------------------------------------------- other tabs
  async function loadPlans() {
    const el = $("#plans");
    try {
      const rows = await call("get_plan_queue",
        { farm: state.farm || null, season: state.season || null });
      $("#plans-meta").textContent = rows.length + " blocks";
      el.innerHTML = rows.map((r) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.block)}</div>
            <div class="qrow__meta">${esc(r.section || "")} · ${num(r.rounds)} rounds ·
              ${num(r.total_kg, 0)} kg · next ${esc(r.next_month || "—")}</div>
          </div>
          <div class="qrow__right">${r.issued
            ? pill(num(r.issued) + " issued", "good") : pill("awaiting store", "warn")}</div>
        </div>`).join("") || `<div class="none">No block has work outstanding.</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load blocks.</div>`; }
  }

  async function loadRequests() {
    const el = $("#requests");
    try {
      const rows = await call("get_store_requests", { farm: state.farm || null });
      $("#req-meta").textContent = rows.length + " requests";
      el.innerHTML = rows.map((r) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.fertilizer_product_name || r.fertilizer_product || r.name)}</div>
            <div class="qrow__meta">${esc(r.block || "")} · ${num(r.quantity)} kg · ${esc(r.name)}</div>
          </div>
          <div class="qrow__right">${pill(r.status || "—",
            r.status === "Approved" || r.status === "Issued" ? "good"
            : r.status === "Rejected" || r.status === "Cancelled" ? "bad" : "warn")}</div>
        </div>`).join("") || `<div class="none">No store requests.</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load requests.</div>`; }
  }

  async function loadApplications() {
    try {
      const rows = await call("get_recent_activity", { farm: state.farm || null });
      $("#apps").innerHTML = rows.map((r) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.fertilizer_product_name || r.fertilizer_product)}</div>
            <div class="qrow__meta">${esc(r.block)} · ${num(r.actual_quantity_applied_kg, 1)} kg ·
              ${esc(r.application_date || "")}</div>
          </div>
          <div class="qrow__right">${r.applied_in_full ? pill("in full", "good") : pill("partial", "warn")}</div>
        </div>`).join("") || `<div class="none">Nothing recorded yet.</div>`;
    } catch (e) { $("#apps").innerHTML = `<div class="none">Could not load applications.</div>`; }

    try {
      const rows = await call("get_variance_alerts", { farm: state.farm || null });
      $("#variance").innerHTML = rows.map((r) => `
        <div class="qrow">
          <div class="qrow__mark">!</div>
          <div>
            <div class="qrow__name">${esc(r.block)} · ${esc(r.fertilizer_product_name || r.fertilizer_product)}</div>
            <div class="qrow__meta">${esc(r.application_date || "")} · ${num(r.variance_pct, 1)}% off plan</div>
          </div>
          <div class="qrow__right">${pill(num(r.variance_pct, 0) + "%", "bad")}</div>
        </div>`).join("") || `<div class="none">Nothing beyond the threshold.</div>`;
    } catch (e) { $("#variance").innerHTML = `<div class="none">Could not load alerts.</div>`; }
  }

  async function loadStock() {
    const el = $("#stock");
    try {
      const rows = await call("get_stock_coverage", { farm: state.farm || null, season: state.season || null });
      el.innerHTML = rows.map((r) => {
        const pct = r.need ? Math.min(100, Math.round((r.stock / r.need) * 100)) : 100;
        return `<div class="hb">
          <div class="hb__name">${esc(r.product_name || r.product)}</div>
          <div class="hb__lane">
            <div class="hb__est"></div>
            <div class="hb__act${r.covered ? "" : " bad"}" style="width:${pct}%"></div>
          </div>
          <div class="hb__pct">${pct}%</div>
        </div>`;
      }).join("") || `<div class="none">No requirement calculated yet.</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load stock cover.</div>`; }
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
      } else if (kind === "send") {
        const r = await call("desk_send_for_review", { programme: c.name });
        toast(`Sent — now ${r.workflow_state}.`, "good");
      }
      await load();
    } catch (e) {
      if (!e.handled) toast(e.message, "bad");
      button.disabled = false; button.textContent = label;
    }
  }

  /** Choosing the item a product is drawn from, with stock in view. */
  async function chooseItem(product) {
    const c = state.data && state.data.current;
    if (!c) return;
    let choices;
    try {
      choices = await call("get_product_choices", { programme: c.name, product });
    } catch (e) { return; }

    const opts = choices.options || [];
    if (!opts.length) {
      toast(`No item matches the search terms on ${product}.`, "bad");
      return;
    }
    const rule = choices.rule;
    const lines = opts.map((o, i) =>
      `${i + 1}. ${o.item_name || o.item_code} — ${num(o.stock_qty)} ${o.stock_uom || "kg"} in stock`
    ).join("\n");
    const ruleText = rule
      ? `\nThe nutrient rule is the same whichever you pick: ${rule.nutrient}, ` +
        `${rule.rate_per_tonne}/tonne, ${rule.bag_weight_kg}kg bag, ${rule.product_nutrient_pct}% content.\n`
      : "";
    const answer = prompt(
      `Which item should ${product} be drawn from?${ruleText}\n${lines}\n\nEnter a number:`,
      String(1 + opts.findIndex((o) => o.item_code === choices.current)) || "1");
    if (!answer) return;
    const pick = opts[parseInt(answer, 10) - 1];
    if (!pick) { toast("That was not one of the options.", "bad"); return; }
    try {
      await call("set_product_item", { programme: c.name, product, item: pick.item_code });
      toast(`${product} will be drawn from ${pick.item_name || pick.item_code}.`, "good");
      await load();
    } catch (e) { /* already surfaced */ }
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
    $("#farm").addEventListener("change", (e) => { state.farm = e.target.value; load(); });
    $("#season").addEventListener("change", (e) => { state.season = e.target.value; load(); });

    // One listener for the whole page: the buttons are re-rendered constantly,
    // so binding them individually would leak handlers on every refresh.
    document.addEventListener("click", (e) => {
      const a = e.target.closest("[data-act]");
      if (a) return act(a);
      const ch = e.target.closest("[data-choose]");
      if (ch) return chooseItem(ch.dataset.choose);
    });

    load().catch(() => {});
  });
})();
