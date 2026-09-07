/* ---------- shared session-page runtime (single source: session_pages/runtime.js) ----------
   Injected between the RUNTIME markers of every page by session_pages.build. Do not edit
   the copy inside a page — edit runtime.js and run `python -m domains.fitness.session_pages --sync`.

   Behaviour (spec: docs/features/reset-cut-training-log/spec.md, Phase 3):
   S1  Reset is per session: clears ticks only, never the weights.
   S2  Weights persist per exercise (localStorage, key rc:<page>:kg, by slug); the last-used
       weight is the next session's default. Build-time TARGETS (from GET /fitness/next-session)
       sit underneath: entered kg > API target > the page's static suggestion.
   S3  Ticks auto-clear on the next open when the stored session date != today.
   S4  Play mode still opens at the first exercise with incomplete ticks (resume mid-session).
*/
const PAGE = document.documentElement.dataset.page || location.pathname.split("/").pop().replace(/\.html$/, "") || "session";
const KEY_TICKS = "rc:" + PAGE + ":ticks", KEY_KG = "rc:" + PAGE + ":kg";
const T = (typeof TARGETS === "object" && TARGETS) || {};
const todayKey = () => { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
const load = (k, fb) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : fb; } catch (e) { return fb; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
const slugOf = e => e.slug || e.d;

/* ---------- state: ticks (today only) + kg (persistent) ---------- */
const storedTicks = load(KEY_TICKS, null);
const ticksToday = storedTicks && storedTicks.date === todayKey() ? (storedTicks.ticks || {}) : {};
const storedKg = load(KEY_KG, {});
const state = ex.map(e => {
  const s = slugOf(e), t = Array.isArray(ticksToday[s]) ? ticksToday[s] : [];
  return { ticks: Array.from({ length: e.sets }, (_, i) => !!t[i]), kg: storedKg[s] != null ? String(storedKg[s]) : "" };
});
function persistTicks() { const o = {}; ex.forEach((e, i) => { o[slugOf(e)] = state[i].ticks; }); save(KEY_TICKS, { date: todayKey(), ticks: o }); }
function persistKg() { const o = {}; ex.forEach((e, i) => { if (state[i].kg !== "") o[slugOf(e)] = state[i].kg; }); save(KEY_KG, o); }

/* ---------- target helpers (API next-session, injected at build) ---------- */
const tgt = e => T.exercises && T.exercises[slugOf(e)] || null;
const fmtKg = v => (v == null ? "" : (Math.round(v * 10) / 10) + " kg");
function suggestKg(e) { const t = tgt(e); return t && t.weight_kg != null ? fmtKg(t.weight_kg) : (e.kg ? e.kg + " kg" : ""); }
function targetLine(e) {
  const t = tgt(e); if (!t) return "";
  const word = { increase: "Up", hold: "Hold", deload: "Deload", start: "Start" }[t.action] || t.action || "";
  const kg = t.weight_kg != null ? fmtKg(t.weight_kg) : (t.action === "increase" && t.last_kg != null ? "one plate up from " + fmtKg(t.last_kg) : "");
  const parts = [kg, t.reason].filter(Boolean).join(" · ");
  return `<div class="tgt ${t.action || ""}"><b>${word}</b>${parts ? " " + parts : ""}</div>`;
}
const play = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
const $ = id => document.getElementById(id);
if (T.generated_at && $("targetsAt")) $("targetsAt").textContent = "targets from " + T.generated_at;

/* ---------- list render ---------- */
const list = $("list");
function renderList() {
  list.innerHTML = "";
  ex.forEach((e, i) => {
    const st = state[i], done = st.ticks.every(Boolean);
    const card = document.createElement("div"); card.className = "ex" + (done ? " done" : "");
    card.innerHTML = `
      <div class="top"><span class="num">${i + 1}</span><span class="name">${e.n}</span><span class="rx">${e.rx}</span></div>
      <p class="cue">${e.cue}</p>${targetLine(e)}
      <div class="row">
        <div class="sets">${st.ticks.map((t, s) => `<button class="set${t ? ' on' : ''}" data-i="${i}" data-s="${s}">${s + 1}</button>`).join("")}</div>
        <input class="kg" inputmode="decimal" data-i="${i}" value="${st.kg}" placeholder="${suggestKg(e) || 'kg'}" aria-label="weight">
        <a class="watch" href="${e.url}" target="_blank" rel="noopener">${play}Watch</a>
      </div>`;
    list.appendChild(card);
  });
}
function toggle(i, s) { state[i].ticks[s] = !state[i].ticks[s]; persistTicks(); renderList(); renderPlay(); }
list.addEventListener("click", ev => { const b = ev.target.closest(".set"); if (b) toggle(+b.dataset.i, +b.dataset.s); });
list.addEventListener("input", ev => { if (ev.target.classList.contains("kg")) { state[+ev.target.dataset.i].kg = ev.target.value; persistKg(); } });
/* S1: reset = ticks only. Weights (state.kg + rc:<page>:kg) are left alone. */
$("reset").onclick = () => { state.forEach(s => { s.ticks.fill(false); }); persistTicks(); renderList(); renderPlay(); };

/* ---------- play render ---------- */
let cur = 0;
function renderPlay() {
  const e = ex[cur], st = state[cur];
  $("pStep").textContent = `${cur + 1} / ${ex.length}`;
  $("pName").textContent = e.n;
  const sk = suggestKg(e);
  $("pRx").innerHTML = `${e.rx}<small>${st.kg ? st.kg + ' kg' : (sk ? 'start ' + sk : '')}</small>`;
  $("pCue").innerHTML = e.cue + targetLine(e);
  const w = $("pWatch"); w.href = e.url; w.innerHTML = play + "Watch the video";
  $("pDiag").innerHTML = (IMG[e.d] ? `<div class="pics">${IMG[e.d].map(u => `<img src="${u}" alt="">`).join("")}</div><div class="cred">${CRED[e.d] || ""}</div>` : D[e.d] || "");
  $("pBody").innerHTML = bodyMap(e.p, e.s);
  $("pMuscles").innerHTML = `<span class="lab">Primary</span>${e.p.map(k => `<b>${mName[k]}</b>`).join(", ")}` +
    (e.s.length ? `<span class="lab">Assisting</span>${e.s.map(k => `<i>${mName[k]}</i>`).join(", ")}` : "");
  $("pSets").innerHTML = st.ticks.map((t, s) => `<button class="set${t ? ' on' : ''}" data-s="${s}">${s + 1}</button>`).join("");
  $("prevBtn").disabled = cur === 0;
  $("nextBtn").textContent = cur === ex.length - 1 ? "Done ✓" : "Next ›";
  $("play-mode").querySelector(".p-body").scrollTop = 0;
}
$("pSets").addEventListener("click", ev => { const b = ev.target.closest(".set"); if (b) toggle(cur, +b.dataset.s); });
$("prevBtn").onclick = () => { if (cur > 0) { cur--; renderPlay(); } };
$("nextBtn").onclick = () => { if (cur < ex.length - 1) { cur++; renderPlay(); } else exit(); };
/* S4: the cursor logic is untouched — first exercise with incomplete ticks. */
$("playBtn").onclick = () => { cur = ex.findIndex((e, i) => !state[i].ticks.every(Boolean)); if (cur < 0) cur = 0; document.body.classList.add("play"); renderPlay(); };
function exit() { document.body.classList.remove("play"); renderList(); }
$("exitBtn").onclick = exit;

renderList();
