// Projektübersicht (I-034) – liest /api/daten, speichert Rückmeldungen per POST (JSON). Kein externes Skript.
"use strict";

const ART_NAMEN = { test: "Test", bug: "Bug", aenderung: "Änderung", idee: "Idee", uebergabe: "Offener Punkt",
                    prompt: "Prompt", frage: "Frage" };
const PRIOS = ["🔴", "🟡", "⚪"];
const STATUS = ["als Nächstes", "zurückstellen", "streichen", "erledigt"];
const STORE_KEY = "okula-projekt-ansicht";

let DATA = null;
const ITEMS = [];          // {el, item, group}
let view = loadView();

// ---------- Hilfsfunktionen ----------

function el(tag, attrs, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;            // nur HTML vom Server (dort escaped)
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children) if (c !== null && c !== undefined) e.append(c);
  return e;
}

function loadView() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
    return { open: v.open || {}, filter: v.filter || {} };
  } catch (e) { return { open: {}, filter: {} }; }
}
function saveView() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(view)); } catch (e) { /* nur Komfort */ }
}

function takenText(v) {
  if (!v) return "";
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return "übernommen " + (m ? `${m[3]}.${m[2]}.` : String(v));
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, Object.assign({ cache: "no-store" }, opts));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.fehler || `Fehler ${r.status}`);
  return data;
}

function flash(span, ok, msg) {
  span.textContent = msg || (ok ? "gespeichert" : "Fehler");
  span.classList.toggle("err", !ok);
  clearTimeout(span._t);
  if (ok) span._t = setTimeout(() => { span.textContent = ""; }, 2500);
}

function fb(key) { return (DATA && DATA.rueckmeldungen[key]) || null; }

// ---------- Laden ----------

async function load() {
  const btn = document.getElementById("reload");
  btn.disabled = true;
  try {
    DATA = await api("api/daten");
    render();
  } catch (e) {
    document.getElementById("hinweise").replaceChildren(
      el("div", { class: "banner err", text: "Daten nicht geladen: " + e.message }));
  } finally {
    btn.disabled = false;
  }
}

function render() {
  ITEMS.length = 0;
  const d = DATA;
  document.getElementById("stand").textContent =
    `Eingelesen ${d.gelesen} · Projektordner ${d.projektordner}` + (d.git ? ` · Git ${d.git}` : "") +
    ` · Rückmeldungen in ${d.datei}`;
  const hints = [];
  if (d.hinweis) hints.push(el("div", { class: "banner", text: d.hinweis }));
  for (const f of d.fehler) hints.push(el("div", { class: "banner err", text: f }));
  if (d.datei_hinweis) hints.push(el("div", { class: "banner err", text: d.datei_hinweis }));
  document.getElementById("hinweise").replaceChildren(...hints);

  const box = document.getElementById("inhalt");
  box.replaceChildren();
  box.append(area("tests", "Tests am realen System", renderTests()));
  for (const art of ["bug", "aenderung", "idee"]) {
    const t = d.tabellen[art];
    if (t) box.append(area(art, t.titel, renderTable(art, t)));
  }
  box.append(area("uebergabe", "Offene Punkte (Übergabe)", renderHandover()));
  box.append(area("prompts", "Prompts", renderPrompts()));
  box.append(area("entscheidungen", "Entscheidungen (nur lesen)", renderDecisions(), false));
  box.append(area("notizen", "Meine neuen Notizen", renderNotes()));
  box.append(area("ohne", "Rückmeldungen ohne Eintrag", renderOrphans()));
  renderOverview();
  applyFilter();
}

function area(id, title, body, openDefault = true) {
  const open = id in view.open ? view.open[id] : openDefault;
  const det = el("details", { class: "area", id: "area-" + id, open },
                 el("summary", {}, title, el("span", { class: "count", id: "count-" + id })),
                 el("div", { class: "body" }, body));
  det.addEventListener("toggle", () => { view.open[id] = det.open; saveView(); });
  return det;
}

function groupBox(id, titleHtml, texts, items) {
  const key = "g-" + id;
  const open = key in view.open ? view.open[key] : true;
  const det = el("details", { class: "group", open },
                 el("summary", {}, el("span", { html: titleHtml }), el("span", { class: "count" })));
  det.addEventListener("toggle", () => { view.open[key] = det.open; saveView(); });
  if (texts && texts.length) det.append(el("div", { class: "group-text" }, ...texts.map(t => el("p", { html: t }))));
  for (const it of items) det.append(it);
  return det;
}

// ---------- Bereiche ----------

function renderTests() {
  const frag = document.createDocumentFragment();
  if (!DATA.tests.length) frag.append(el("p", { class: "muted", text: "Keine offenen Tests gefunden." }));
  for (const g of DATA.tests) {
    const els = g.items.map(it => itemEl(it, g));
    if (!els.length) continue;           // Abschnitt ohne offene Punkte („alle geprüft“)
    const box = groupBox("t-" + g.id, g.titel_html, g.text_html, els);
    box.dataset.group = g.id;
    frag.append(box);
  }
  return frag;
}

function renderTable(art, t) {
  const frag = document.createDocumentFragment();
  if (!t.items.length) frag.append(el("p", { class: "muted", text: "Keine offenen Einträge." }));
  for (const it of t.items) frag.append(itemEl(it));
  return frag;
}

function renderHandover() {
  const frag = document.createDocumentFragment();
  const u = DATA.uebergabe;
  if (u.titel) frag.append(el("p", { class: "muted", text: u.titel }));
  if (!u.items.length) frag.append(el("p", { class: "muted", text: "Keine offenen Punkte gefunden." }));
  for (const it of u.items) frag.append(itemEl(it));
  return frag;
}

function renderPrompts() {
  const frag = document.createDocumentFragment();
  for (const it of DATA.prompts) frag.append(itemEl(it));
  return frag;
}

function renderDecisions() {
  return el("ul", { class: "plain" }, ...DATA.entscheidungen.map(h => el("li", { html: h })));
}

// ---------- Ein Eintrag ----------

function itemEl(it, group) {
  const row = el("div", { class: "item" });
  row.dataset.art = it.art;
  const txt = el("div", { class: "txt" });
  if (it.art === "bug" || it.art === "aenderung" || it.art === "idee") {
    txt.append(el("span", { class: "id", text: it.id }), el("span", { class: "tag", text: it.prio || "–" }),
               el("span", { class: "tag", text: it.status || "–" }), el("span", { html: it.html }));
    const extra = it.spalten.filter(([c]) => !["ID", "Prio", "Status", "Beschreibung"].includes(c));
    if (extra.length) txt.append(el("div", { class: "cols" },
      ...extra.map(([c, v]) => el("span", {}, c + ": ", el("span", { html: v })))));
  } else if (it.art === "prompt") {
    txt.append(el("span", { class: "id", text: it.datei }), el("div", { html: it.html }),
               el("div", { class: "meta", text: "Status: " + (it.status || "–") }));
  } else if (it.art === "uebergabe") {
    txt.append(el("span", { class: "id", text: it.nr + "." }), el("span", { html: it.html }));
  } else {
    txt.append(el("span", { html: it.html }));
  }
  const ctl = el("div", { class: "ctl" });
  const saved = el("span", { class: "saved" });
  const meta = el("div", { class: "meta" });
  const send = async (changes) => {
    try {
      const r = await api("api/rueckmeldung", Object.assign(
        { key: it.key, art: it.art, bezug: it.bezug, text: it.text }, changes));
      if (r.eintrag) DATA.rueckmeldungen[it.key] = r.eintrag; else delete DATA.rueckmeldungen[it.key];
      flash(saved, true);
      refresh();
      renderOverview();
      applyFilter();
    } catch (e) { flash(saved, false, e.message); }
  };
  const btns = {};
  if (it.art === "test") {
    const r = el("div", { class: "row" });
    for (const [v, label] of [["ok", "✔ ok"], ["fehler", "✖ Fehler"]]) {
      btns[v] = el("button", { type: "button", class: "tbtn", text: label,
        title: v === "ok" ? "Test bestanden (nochmals klicken = leer)" : "Test mit Fehler (Kommentar ergänzen)",
        onclick: () => send({ haken: (fb(it.key) || {}).haken === v ? null : v }) });
      r.append(btns[v]);
    }
    r.append(saved);
    ctl.append(r);
  }
  let prio = null, status = null;
  if (["bug", "aenderung", "idee"].includes(it.art)) {
    prio = el("select", { title: "Wunsch-Priorität", onchange: () => send({ prio_wunsch: prio.value || null }) },
              el("option", { value: "", text: "Prio-Wunsch –" }), ...PRIOS.map(p => el("option", { value: p, text: p })));
    status = el("select", { title: "Wunsch-Status", onchange: () => send({ status_wunsch: status.value || null }) },
                el("option", { value: "", text: "Status-Wunsch –" }),
                ...STATUS.map(s => el("option", { value: s, text: s })));
    ctl.append(el("div", { class: "row" }, prio, status, saved));
  } else if (it.art !== "test") {
    ctl.append(el("div", { class: "row" }, saved));
  }
  const comment = el("textarea", { rows: 1, placeholder: "Kommentar …" });
  let timer = null;
  const saveComment = () => {
    clearTimeout(timer);
    const cur = (fb(it.key) || {}).kommentar || "";
    if (comment.value.trim() !== cur.trim()) send({ kommentar: comment.value });
  };
  comment.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(saveComment, 1200); });
  comment.addEventListener("change", saveComment);
  ctl.append(comment, meta);
  row.append(txt, ctl);

  function refresh() {
    const f = fb(it.key);
    row.classList.toggle("doc-done", !!it.erledigt);
    row.classList.toggle("has-fb", !!f);
    row.classList.toggle("taken", !!(f && f.uebernommen));
    for (const [v, b] of Object.entries(btns)) b.classList.toggle("on-" + v, !!(f && f.haken === v));
    if (prio) prio.value = (f && f.prio_wunsch) || "";
    if (status) status.value = (f && f.status_wunsch) || "";
    if (document.activeElement !== comment) comment.value = (f && f.kommentar) || "";
    const parts = [];
    if (f && f.prio_wunsch) parts.push(`Prio ${it.prio || "–"} → Wunsch ${f.prio_wunsch}`);
    if (f && f.status_wunsch) parts.push(`Status ${it.status || "–"} → Wunsch ${f.status_wunsch}`);
    if (f && f.uebernommen) parts.push(takenText(f.uebernommen));
    else if (f && f.geaendert) parts.push("neu · geändert " + f.geaendert.replace("T", " ").slice(0, 16));
    meta.textContent = parts.join(" · ");
  }
  refresh();
  ITEMS.push({ el: row, item: it, group });
  return row;
}

// ---------- Notizen und verwaiste Rückmeldungen ----------

function renderNotes() {
  const frag = document.createDocumentFragment();
  if (!DATA.notizen.length) frag.append(el("p", { class: "muted", text: "Noch keine Notizen. Neue Notiz: Feld oben." }));
  for (const n of DATA.notizen) {
    const saved = el("span", { class: "saved" });
    const art = el("select", { disabled: !!n.uebernommen },
                   ...["bug", "aenderung", "idee", "frage"].map(a => el("option", { value: a, text: ART_NAMEN[a] })));
    art.value = n.art;
    const text = el("textarea", { rows: 2, disabled: !!n.uebernommen });
    text.value = n.text;
    const row = el("div", { class: "item" + (n.uebernommen ? " taken" : "") });
    row.dataset.art = "notiz";
    const ctl = el("div", { class: "ctl" });
    if (n.uebernommen) {
      ctl.append(el("span", { class: "taken-mark", text: takenText(n.uebernommen) }));
    } else {
      ctl.append(el("div", { class: "row" },
        el("button", { type: "button", text: "Speichern", onclick: async () => {
          try { await api("api/notiz", { aktion: "aendern", id: n.id, art: art.value, text: text.value });
                flash(saved, true); n.art = art.value; n.text = text.value; } catch (e) { flash(saved, false, e.message); }
        } }),
        el("button", { type: "button", text: "Löschen", onclick: async () => {
          if (!confirm("Notiz löschen?")) return;
          try { await api("api/notiz", { aktion: "loeschen", id: n.id }); await load(); }
          catch (e) { flash(saved, false, e.message); }
        } }), saved));
    }
    ctl.append(el("div", { class: "meta", text: "erstellt " + n.erstellt.replace("T", " ").slice(0, 16) }));
    row.append(el("div", { class: "txt" }, art, text), ctl);
    frag.append(row);
  }
  return frag;
}

function renderOrphans() {
  const frag = document.createDocumentFragment();
  frag.append(el("p", { class: "muted", text: "Rückmeldungen, deren Eintrag in der Doku geändert oder entfernt " +
    "wurde (oder schon übernommen ist). Sie bleiben in der Datei erhalten." }));
  if (!DATA.ohne_eintrag.length) frag.append(el("p", { class: "muted", text: "Keine." }));
  for (const key of DATA.ohne_eintrag) {
    const f = DATA.rueckmeldungen[key];
    const parts = [];
    if (f.haken) parts.push("Häkchen: " + f.haken);
    if (f.prio_wunsch) parts.push("Prio-Wunsch " + f.prio_wunsch);
    if (f.status_wunsch) parts.push("Status-Wunsch " + f.status_wunsch);
    if (f.kommentar) parts.push("Kommentar: " + f.kommentar);
    const row = el("div", { class: "item orphan" + (f.uebernommen ? " taken" : "") },
      el("div", { class: "txt" }, el("span", { class: "id", text: `${ART_NAMEN[f.art] || f.art} · ${f.bezug}` }),
         el("span", { text: f.text })),
      el("div", { class: "ctl" }, el("div", { text: parts.join(" · ") }),
         el("div", { class: "meta", text: f.uebernommen ? takenText(f.uebernommen) : "geändert " +
           String(f.geaendert || "").replace("T", " ").slice(0, 16) })));
    row.dataset.art = "ohne";
    frag.append(row);
  }
  return frag;
}

// ---------- Übersicht ----------

function isNew(f) { return f && !f.uebernommen; }

function renderOverview() {
  const d = DATA;
  const box = document.getElementById("uebersicht");
  const testRows = [];
  let sum = [0, 0, 0];
  for (const g of d.tests) {
    let open = 0, ok = 0, err = 0;
    for (const it of g.items) {
      const f = fb(it.key);
      if (f && f.haken === "ok") ok++;
      else if (f && f.haken === "fehler") err++;
      else if (!it.erledigt) open++;
    }
    if (!g.items.length) continue;
    sum = [sum[0] + open, sum[1] + ok, sum[2] + err];
    testRows.push(el("tr", {}, el("td", { text: g.id === "vorbereitung" ? "Vorbereitung" : "Abschnitt " + g.id }),
      el("td", { class: "n", text: open }), el("td", { class: "n num-ok", text: ok || "" }),
      el("td", { class: "n num-err", text: err || "" })));
  }
  testRows.push(el("tr", {}, el("th", { text: "Summe" }), el("th", { class: "n", text: sum[0] }),
    el("th", { class: "n num-ok", text: sum[1] }), el("th", { class: "n num-err", text: sum[2] })));
  const tests = el("div", {}, el("h2", { text: "Tests am realen System" }),
    el("table", {}, el("tr", {}, el("th", { text: "Abschnitt" }), el("th", { class: "n", text: "offen" }),
      el("th", { class: "n", text: "✔ ok" }), el("th", { class: "n", text: "✖ Fehler" })), ...testRows));

  const newCount = Object.values(d.rueckmeldungen).filter(isNew).length +
                   d.notizen.filter(n => !n.uebernommen).length;
  const lists = el("div", {}, el("h2", { text: "Offen" }),
    el("table", {}, ...["bug", "aenderung", "idee"].filter(a => d.tabellen[a]).map(a =>
      el("tr", {}, el("td", { text: d.tabellen[a].titel }), el("td", { class: "n big", text: d.tabellen[a].items.length }))),
      el("tr", {}, el("td", { text: "Offene Punkte (Übergabe)" }), el("td", { class: "n big", text: d.uebergabe.items.length })),
      el("tr", {}, el("td", { text: "Neue Rückmeldungen (nicht übernommen)" }),
         el("td", { class: "n big", text: newCount }))));

  const prompts = el("div", {}, el("h2", { text: "Prompts" }),
    el("table", {}, ...d.prompts.map(p => el("tr", {}, el("td", { text: p.datei.replace(/\.md$/, "") }),
      el("td", { text: p.status_kurz || "–" })))));

  const next = el("div", { class: "ov-next" });
  if (d.kurz.als_naechstes) next.append(el("p", {}, el("b", { text: "Als Nächstes: " }), el("span", { html: d.kurz.als_naechstes })));
  if (d.kurz.vorschlag) next.append(el("p", { html: d.kurz.vorschlag }));
  box.replaceChildren(el("div", { class: "ov-grid" }, tests, lists, prompts), next);

  // Zähler in den Bereichen
  const setCount = (id, n) => { const c = document.getElementById("count-" + id); if (c) c.textContent = n; };
  setCount("tests", `${sum[0]} offen`);
  for (const a of ["bug", "aenderung", "idee"]) if (d.tabellen[a]) setCount(a, d.tabellen[a].items.length);
  setCount("uebergabe", d.uebergabe.items.length);
  setCount("prompts", d.prompts.length);
  setCount("entscheidungen", d.entscheidungen.length);
  setCount("notizen", d.notizen.length);
  setCount("ohne", d.ohne_eintrag.length);
}

// ---------- Suche und Filter ----------

function readFilter() {
  return {
    q: document.getElementById("suche").value.trim().toLowerCase(),
    arten: [...document.querySelectorAll("#filter-art input")].filter(i => i.checked).map(i => i.value),
    prio: document.getElementById("filter-prio").value,
    meine: document.getElementById("filter-meine").checked,
    neu: document.getElementById("filter-neu").checked,
    erledigt: document.getElementById("filter-erledigt").checked,
  };
}

function writeFilter(f) {
  document.getElementById("suche").value = f.q || "";
  if (Array.isArray(f.arten))
    for (const i of document.querySelectorAll("#filter-art input")) i.checked = f.arten.includes(i.value);
  document.getElementById("filter-prio").value = f.prio || "";
  document.getElementById("filter-meine").checked = !!f.meine;
  document.getElementById("filter-neu").checked = !!f.neu;
  document.getElementById("filter-erledigt").checked = !!f.erledigt;
}

function applyFilter() {
  if (!DATA) return;
  const f = readFilter();
  view.filter = f;
  saveView();
  const words = f.q.split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const { el: row, item: it } of ITEMS) {
    const r = fb(it.key);
    let ok = f.arten.includes(it.art);
    if (ok && f.prio) ok = it.prio === f.prio || !!(r && r.prio_wunsch === f.prio);
    if (ok && f.meine) ok = !!r;
    if (ok && f.neu) ok = isNew(r);
    if (ok && f.erledigt && it.art === "test") ok = !it.erledigt && !(r && r.haken === "ok");
    if (ok && words.length) {
      const hay = [it.text, it.bezug, it.id, it.status, r && r.kommentar].filter(Boolean).join(" ").toLowerCase();
      ok = words.every(w => hay.includes(w));
    }
    row.hidden = !ok;
    if (ok) shown++;
  }
  // Notizen und verwaiste Rückmeldungen: nur Suche
  for (const row of document.querySelectorAll('.item[data-art="notiz"], .item[data-art="ohne"]')) {
    const hay = (row.textContent + " " + [...row.querySelectorAll("textarea")].map(t => t.value).join(" ")).toLowerCase();
    row.hidden = !words.every(w => hay.includes(w));
  }
  for (const g of document.querySelectorAll("details.group"))
    g.hidden = ![...g.querySelectorAll(".item")].some(i => !i.hidden);
  const areaArt = { tests: ["test"], bug: ["bug"], aenderung: ["aenderung"], idee: ["idee"],
                    uebergabe: ["uebergabe"], prompts: ["prompt"] };
  for (const [id, arts] of Object.entries(areaArt)) {
    const a = document.getElementById("area-" + id);
    if (a) a.hidden = !arts.some(x => f.arten.includes(x));
  }
  const filtered = words.length || f.prio || f.meine || f.neu || f.erledigt || f.arten.length < 6;
  document.getElementById("treffer").textContent = filtered ? `${shown} Einträge sichtbar` : "";
}

// ---------- Start ----------

document.addEventListener("DOMContentLoaded", () => {
  writeFilter(view.filter);
  document.getElementById("reload").addEventListener("click", load);
  document.getElementById("suche").addEventListener("input", applyFilter);
  for (const i of document.querySelectorAll("#filter input, #filter select"))
    if (i.id !== "suche") i.addEventListener("change", applyFilter);
  document.getElementById("notiz-speichern").addEventListener("click", async () => {
    const text = document.getElementById("notiz-text");
    const status = document.getElementById("notiz-status");
    if (!text.value.trim()) { flash(status, false, "Text fehlt"); return; }
    try {
      await api("api/notiz", { aktion: "neu", art: document.getElementById("notiz-art").value, text: text.value });
      text.value = "";
      flash(status, true);
      await load();
    } catch (e) { flash(status, false, e.message); }
  });
  load();
});
