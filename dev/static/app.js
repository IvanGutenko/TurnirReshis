"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (x) => Math.round(x).toLocaleString("ru-RU");
let authMode = "login";
let routes = [];
let priceTouched = false;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Ошибка ${res.status}`), { status: res.status });
  return data;
}

// ---------- авторизация ----------
function showAuth() {
  $("auth").hidden = false; $("app").hidden = true; $("userbox").hidden = true;
}
async function showApp(login) {
  $("auth").hidden = true; $("app").hidden = false; $("userbox").hidden = false;
  $("username").textContent = login;
  if (!routes.length) await loadRoutes();
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  authMode = tab.dataset.mode;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
  $("authsubmit").textContent = authMode === "login" ? "Войти" : "Зарегистрироваться";
  $("authform").password.autocomplete = authMode === "login" ? "current-password" : "new-password";
  $("autherror").textContent = "";
}));

$("authform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  $("autherror").textContent = "";
  $("authsubmit").disabled = true;
  try {
    const r = await api(`/api/${authMode}`, { login: f.login.value.trim(), password: f.password.value });
    f.password.value = "";
    await showApp(r.login);
  } catch (err) {
    $("autherror").textContent = err.message;
  } finally {
    $("authsubmit").disabled = false;
  }
});

$("logout").addEventListener("click", async () => {
  await api("/api/logout", {});
  $("result").hidden = true;
  showAuth();
});

// ---------- форма прогноза ----------
const cityName = (r, i) => r.name.split(" — ")[i];

async function loadRoutes() {
  const data = await api("/api/routes");
  routes = data.routes;
  $("source").textContent = `Источник прогноза: ${data.source}. Даты: ${data.dates[0]} — ${data.dates[data.dates.length - 1]}.`;
  const origins = [...new Map(routes.map((r) => [r.origin, cityName(r, 0)])).entries()];
  $("origin").replaceChildren(...origins.map(([code, name]) => new Option(name, code)));
  $("date").min = data.dates[0];
  $("date").max = data.dates[data.dates.length - 1];
  $("date").value = data.dates.includes("2026-06-12") ? "2026-06-12" : data.dates[0];
  fillDestinations();
}

function fillDestinations() {
  const list = routes.filter((r) => r.origin === $("origin").value);
  $("destination").replaceChildren(...list.map((r) => new Option(cityName(r, 1), r.destination)));
  setBasePrice();
}

function currentRoute() {
  return routes.find((r) => r.origin === $("origin").value && r.destination === $("destination").value);
}

function setBasePrice() {
  const r = currentRoute();
  if (r && !priceTouched) $("price").value = r.base_price;
}

$("origin").addEventListener("change", fillDestinations);
$("destination").addEventListener("change", () => { priceTouched = false; setBasePrice(); });
$("price").addEventListener("input", () => { priceTouched = true; });

$("fform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  $("ferror").textContent = "";
  try {
    const r = await api("/api/forecast", {
      origin: f.origin.value, destination: f.destination.value, date: f.date.value, price: f.price.value,
    });
    render(r);
  } catch (err) {
    if (err.status === 401) { showAuth(); $("autherror").textContent = err.message; return; }
    $("ferror").textContent = err.message;
  }
});

// ---------- результат ----------
function render(r) {
  $("result").hidden = false;
  $("s-seats").textContent = fmt(r.seats);
  $("s-want").textContent = fmt(r.want);
  $("s-buy").textContent = fmt(r.buy);
  $("s-free").textContent = fmt(r.free_seats);
  $("chart-title").textContent = `${r.route_name}, ${new Date(r.date).toLocaleDateString("ru-RU")}, цена ${fmt(r.price)} ₽`;
  drawChart(r);

  const s = r.scenarios, lo = s[0].want, hi = s[s.length - 1].want;
  const parts = [`С вероятностью 80% при этой цене захотят купить от ${fmt(Math.max(0, lo))} до ${fmt(Math.max(0, hi))} человек.`];
  if (r.sold_out_scenarios === 0) parts.push("Ни в одном сценарии продажи не упираются в число мест.");
  else if (r.sold_out_scenarios === s.length) parts.push("Во всех сценариях желающих больше, чем мест: самолёт заполнится, цену можно поднять.");
  else parts.push(`В ${r.sold_out_scenarios} из 9 сценариев желающих больше, чем мест (вероятность примерно ${r.sold_out_scenarios * 10}%).`);
  if (r.optimal_price_median) parts.push(`Лучшая цена по медианному прогнозу: ${fmt(r.optimal_price_median)} ₽ (базовая ${fmt(r.base_price)} ₽).`);
  $("chart-note").textContent = parts.join(" ");

  $("table").tBodies[0].replaceChildren(...s.map((x) => {
    const tr = document.createElement("tr");
    if (x.quantile === 0.5) tr.className = "median";
    [x.quantile.toFixed(1), fmt(x.base_demand), fmt(x.want), fmt(x.buy)].forEach((v) => {
      const td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
    });
    return tr;
  }));
}

const SVG = "http://www.w3.org/2000/svg";
function el(name, attrs, text) {
  const n = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}

function niceStep(max) {
  const raw = max / 5, pow = 10 ** Math.floor(Math.log10(raw)), n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

function drawChart(r) {
  const narrow = $("chart").clientWidth < 600;
  const W = narrow ? 420 : 860, H = narrow ? 300 : 330, L = 44, R = narrow ? 44 : 70, T = 18, B = 52;
  const fs = narrow ? 9.5 : 12;
  const s = r.scenarios;
  const yMax = Math.max(r.seats, ...s.map((x) => x.want), 1) * 1.1;
  const step = niceStep(yMax);
  const y = (v) => T + (H - T - B) * (1 - v / yMax);
  const slot = (W - L - R) / s.length, bw = slot * 0.62;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });

  for (let v = 0; v <= yMax; v += step) {
    svg.append(el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }));
    svg.append(el("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", style: `font-size:${fs}px` }, fmt(v)));
  }
  s.forEach((x, i) => {
    const cx = L + slot * i + slot / 2, want = Math.max(0, x.want);
    const below = Math.min(want, r.seats);
    svg.append(el("rect", { x: cx - bw / 2, y: y(below), width: bw, height: y(0) - y(below), fill: "var(--want)", rx: 3,
      opacity: x.quantile === 0.5 ? 1 : 0.72 }));
    if (want > r.seats) {
      svg.append(el("rect", { x: cx - bw / 2, y: y(want), width: bw, height: y(r.seats) - y(want), fill: "var(--over)", rx: 3 }));
    }
    svg.append(el("text", { x: cx, y: y(want) - 6, "text-anchor": "middle", class: "val",
      "font-weight": x.quantile === 0.5 ? 700 : 400, style: `font-size:${fs}px` }, fmt(want)));
    svg.append(el("text", { x: cx, y: H - B + 18, "text-anchor": "middle", style: `font-size:${fs}px` }, x.quantile.toFixed(1)));
  });
  const caption = narrow ? [[0, "песс."], [4, "медиана"], [8, "оптим."]] : [[0, "пессимистичный"], [4, "медиана"], [8, "оптимистичный"]];
  caption.forEach(([i, t]) => svg.append(el("text", { x: L + slot * i + slot / 2, y: H - B + 36, "text-anchor": "middle", style: `font-size:${fs}px` }, t)));
  svg.append(el("line", { x1: L, x2: W - R, y1: y(r.seats), y2: y(r.seats), stroke: "var(--seats)", "stroke-width": 2, "stroke-dasharray": "6 5" }));
  svg.append(el("text", { x: W - R + 6, y: y(r.seats) + 4, style: `fill: var(--seats); font-size:${fs}px` }, narrow ? fmt(r.seats) : `мест: ${fmt(r.seats)}`));
  $("chart").replaceChildren(svg);
}

// ---------- старт ----------
api("/api/me").then((r) => (r.login ? showApp(r.login) : showAuth())).catch(showAuth);
