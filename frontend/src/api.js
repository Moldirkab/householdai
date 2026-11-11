const KEY = "householdai_token";

export const getToken = () => localStorage.getItem(KEY);
export const setToken = (t) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY));

export async function api(path, { method = "GET", body, raw = false } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (raw) return res;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join("; ");
    const err = new Error(msg || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---------- formatting ----------
export function money(v, cur = "₸") {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Math.round(v);
  if (cur === "$") return (n < 0 ? "−$" : "$") + Math.abs(n).toLocaleString("en-US");
  return (n < 0 ? "−" : "") + Math.abs(n).toLocaleString("en-US").replace(/,/g, " ") + " " + cur;
}
export const pct = (v) => (v === null || v === undefined ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%");

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthLabel = (m) => `${MONTHS[parseInt(m.slice(5), 10) - 1]} ${m.slice(0, 4)}`;
export function monthAdd(m, k) {
  const t = parseInt(m.slice(0, 4), 10) * 12 + parseInt(m.slice(5), 10) - 1 + k;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
}
export const thisMonth = () => new Date().toISOString().slice(0, 7);
export const today = () => new Date().toISOString().slice(0, 10);

const COLORS = ["#0f766e", "#7a5c1f", "#5b4a9a", "#9a3b5b", "#2d5f9a", "#4b6b1f"];
export const memberColor = (i) => COLORS[i % COLORS.length];
export const statusColor = (s) => (s === "over" ? "var(--over)" : s === "under" ? "var(--under)" : s === "ok" ? "var(--ok)" : "var(--muted)");
