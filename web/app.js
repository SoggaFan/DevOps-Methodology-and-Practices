const $ = (id) => document.getElementById(id);
const state = { boats: [], crews: [], fish: [], trips: [] };

function showMessage(text, error = false) {
  const box = $("message");
  box.textContent = text;
  box.className = `message${error ? " error" : ""}`;
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => box.classList.add("hidden"), 5000);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map(x => x.msg).join("; ") : (body.detail || `HTTP ${response.status}`);
    throw new Error(detail);
  }
  return body;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function asNumberPayload(data, fields) {
  for (const field of fields) data[field] = Number(data[field]);
  return data;
}

function renderTable(target, headers, rows) {
  if (!rows.length) { target.innerHTML = '<div class="empty">Нет данных.</div>'; return; }
  target.innerHTML = `<table class="data-table"><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(v => `<td>${v ?? "—"}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function fillSelect(id, items, labelFn) {
  const select = $(id);
  select.innerHTML = '<option value="">Выберите…</option>' + items.map(x => `<option value="${x.id}">${labelFn(x)}</option>`).join("");
}

async function loadBoats() {
  state.boats = await api("/api/boats");
  renderTable($("boats-list"), ["ID", "Название", "Рег. №", "Вместимость, кг"], state.boats.map(x => [x.id, x.name, x.registration_no, x.capacity_kg]));
  fillSelect("boat-select", state.boats, x => `${x.name} · ${x.capacity_kg} кг`);
}
async function loadCrews() {
  state.crews = await api("/api/crews");
  renderTable($("crews-list"), ["ID", "Команда", "Капитан"], state.crews.map(x => [x.id, x.name, x.captain]));
  fillSelect("crew-select", state.crews, x => `${x.name} · ${x.captain}`);
}
async function loadFish() {
  state.fish = await api("/api/fish-types");
  renderTable($("fish-list"), ["ID", "Название", "Latin"], state.fish.map(x => [x.id, x.name, x.latin_name || "—"]));
  fillSelect("fish-select", state.fish, x => x.latin_name ? `${x.name} (${x.latin_name})` : x.name);
}
async function loadTrips() {
  state.trips = await api("/api/trips");
  const boatName = new Map(state.boats.map(x => [x.id, x.name]));
  const crewName = new Map(state.crews.map(x => [x.id, x.name]));
  renderTable($("trips-list"), ["ID", "Катер", "Команда", "Выход", "Возврат"], state.trips.map(x => [x.id, boatName.get(x.boat_id) || `#${x.boat_id}`, crewName.get(x.crew_id) || `#${x.crew_id}`, x.departure_date, x.return_date || "—"]));
  fillSelect("trip-select", state.trips, x => `#${x.id} · ${boatName.get(x.boat_id) || "катер"} · ${x.departure_date}`);
}
async function loadReport() {
  const params = new URLSearchParams();
  if ($("report-from").value) params.set("date_from", $("report-from").value);
  if ($("report-to").value) params.set("date_to", $("report-to").value);
  const rows = await api(`/api/reports/catch-by-period${params.toString() ? `?${params}` : ""}`);
  renderTable($("report-list"), ["Рейс", "Катер", "Дата выхода", "Вес улова, кг"], rows.map(x => [x.trip_id, x.boat, x.departure_date, x.total_weight_kg]));
}
async function loadHealth() {
  try { await api("/health"); $("health-dot").style.background = "#48bb78"; $("health-text").textContent = "БД и API работают"; }
  catch (e) { $("health-dot").style.background = "#e53e3e"; $("health-text").textContent = "Ошибка подключения"; }
}

async function refreshAll() {
  try {
    await Promise.all([loadBoats(), loadCrews(), loadFish()]);
    await loadTrips();
    await loadReport();
    await loadHealth();
  } catch (e) { showMessage(e.message, true); }
}

$("boat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { const d = asNumberPayload(formData(e.target), ["capacity_kg"]); await api("/api/boats", { method: "POST", body: JSON.stringify(d) }); e.target.reset(); showMessage("Катер добавлен."); await Promise.all([loadBoats(), loadTrips()]); }
  catch (err) { showMessage(err.message, true); }
});
$("crew-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { await api("/api/crews", { method: "POST", body: JSON.stringify(formData(e.target)) }); e.target.reset(); showMessage("Команда добавлена."); await Promise.all([loadCrews(), loadTrips()]); }
  catch (err) { showMessage(err.message, true); }
});
$("fish-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { const d = formData(e.target); if (!d.latin_name) d.latin_name = null; await api("/api/fish-types", { method: "POST", body: JSON.stringify(d) }); e.target.reset(); showMessage("Сорт рыбы добавлен."); await loadFish(); }
  catch (err) { showMessage(err.message, true); }
});
$("trip-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { const d = formData(e.target); if (!d.return_date) d.return_date = null; if (!d.notes) d.notes = null; d.boat_id = Number(d.boat_id); d.crew_id = Number(d.crew_id); await api("/api/trips", { method: "POST", body: JSON.stringify(d) }); e.target.reset(); showMessage("Рейс создан."); await loadTrips(); await loadReport(); }
  catch (err) { showMessage(err.message, true); }
});
$("catch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { const d = asNumberPayload(formData(e.target), ["trip_id", "fish_type_id", "cans", "weight_kg"]); await api("/api/catches", { method: "POST", body: JSON.stringify(d) }); e.target.reset(); showMessage("Улов добавлен."); await loadReport(); }
  catch (err) { showMessage(err.message, true); }
});

$("reload-boats").onclick = () => loadBoats().catch(e => showMessage(e.message, true));
$("reload-crews").onclick = () => loadCrews().catch(e => showMessage(e.message, true));
$("reload-fish").onclick = () => loadFish().catch(e => showMessage(e.message, true));
$("reload-trips").onclick = () => loadTrips().catch(e => showMessage(e.message, true));
$("reload-report").onclick = () => loadReport().catch(e => showMessage(e.message, true));
$("report-from").onchange = () => loadReport().catch(e => showMessage(e.message, true));
$("report-to").onchange = () => loadReport().catch(e => showMessage(e.message, true));

refreshAll();
