import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, memberColor, setToken } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox } from "../components/ui.jsx";

export default function HouseholdPage() {
  const { me, household, hid, refreshHousehold, refreshMe, setMe } = useApp();
  const nav = useNavigate();
  const owner = household.my_role === "owner";
  const [name, setName] = useState(household.name);
  const [currency, setCurrency] = useState(household.currency);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const run = async (fn, ok) => {
    setError(""); setMsg("");
    try { await fn(); if (ok) setMsg(ok); await refreshHousehold(); } catch (e) { setError(e.message); }
  };
  const exportCsv = async () => {
    const res = await api(`/households/${hid}/export.csv`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `${household.name}_expenses.csv` });
    a.click(); URL.revokeObjectURL(url);
  };
  const leave = async () => {
    if (!window.confirm("Leave this household? You will lose access to its budget.")) return;
    try { await api(`/households/${hid}/members/${me.id}`, { method: "DELETE" }); await refreshMe(); nav("/"); } catch (e) { setError(e.message); }
  };
  const deleteAccount = async () => {
    if (!window.confirm("Delete your account permanently? Households where you are the only member are deleted too.")) return;
    try { await api("/me", { method: "DELETE" }); setToken(null); setMe(null); nav("/login"); } catch (e) { setError(e.message); }
  };

  return (
    <div className="wrap" style={{ maxWidth: 900 }}>
      <header className="page"><div><div className="eyebrow">Household</div><h1>{household.name}</h1>
        <div className="sub">Members, roles and settings. Owners manage members; members add expenses and plans; viewers can only look.</div></div></header>
      <ErrorBox error={error} />
      {msg && <div className="note">{msg}</div>}

      <div className="card">
        <h3>Members</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th /></tr></thead>
          <tbody>{household.members.map((m, i) => (
            <tr key={m.user_id}>
              <td><span className="member" style={{ border: 0, padding: 0 }}><span className="av" style={{ background: memberColor(i) }}>{m.name[0]}</span>{m.name}{m.user_id === me.id ? " (you)" : ""}</span></td>
              <td className="sub">{m.email}</td>
              <td>{owner ? (
                <select aria-label={`Role of ${m.name}`} value={m.role}
                  onChange={(e) => run(() => api(`/households/${hid}/members/${m.user_id}`, { method: "PATCH", body: { role: e.target.value } }), "Role updated.")}>
                  <option value="owner">owner</option><option value="member">member</option><option value="viewer">viewer</option>
                </select>) : <span className="chip role">{m.role}</span>}</td>
              <td>{owner && m.user_id !== me.id && (
                <button className="small danger" onClick={() => window.confirm(`Remove ${m.name} from the household?`) &&
                  run(() => api(`/households/${hid}/members/${m.user_id}`, { method: "DELETE" }), "Member removed.")}>Remove</button>)}</td>
            </tr>))}</tbody>
        </table></div>
      </div>

      {household.invite_code && (
        <div className="card">
          <h3>Invite someone</h3>
          <p className="sub">Share this code. The person creates an account, chooses “Join with an invite code” and becomes a member.</p>
          <div className="row">
            <span className="num" style={{ fontSize: 22, letterSpacing: ".1em" }}>{household.invite_code}</span>
            <button onClick={() => navigator.clipboard?.writeText(household.invite_code).then(() => setMsg("Code copied."), () => {})}>Copy</button>
            {owner && <button onClick={() => run(() => api(`/households/${hid}/invite/regenerate`, { method: "POST" }), "New code created. The old code no longer works.")}>New code</button>}
          </div>
        </div>
      )}

      {owner && (
        <form className="card" onSubmit={(e) => { e.preventDefault(); run(() => api(`/households/${hid}`, { method: "PATCH", body: { name, currency } }), "Settings saved."); }}>
          <h3>Settings</h3>
          <div className="row">
            <label className="field" htmlFor="sname">Household name<input id="sname" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field" htmlFor="scur">Currency<select id="scur" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="₸">₸ Tenge</option><option value="$">$ US dollar</option><option value="€">€ Euro</option><option value="₽">₽ Ruble</option></select></label>
            <button className="primary">Save</button>
          </div>
        </form>
      )}

      <div className="card">
        <h3>Your data</h3>
        <div className="row">
          <button onClick={exportCsv}>Export expenses (CSV)</button>
          <button className="danger" onClick={leave}>Leave household</button>
          <button className="danger" onClick={deleteAccount}>Delete my account</button>
        </div>
        <p className="sub">Expenses are stored only in this app's local database. No bank connection is used.</p>
      </div>
    </div>
  );
}
