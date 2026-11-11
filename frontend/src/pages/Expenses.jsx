import React, { useCallback, useEffect, useState } from "react";
import { api, money, monthAdd, monthLabel, thisMonth, today } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox } from "../components/ui.jsx";

const empty = (meId) => ({ amount: "", category: "Food", spent_on: today(), note: "", shared: true, paid_by: meId });

export default function Expenses() {
  const { me, household, hid } = useApp();
  const cur = household.currency;
  const canWrite = household.my_role !== "viewer" && household.data_source !== "bls";
  const { refreshHousehold } = useApp();
  const [month, setMonth] = useState(household.latest_month || thisMonth());
  const [cat, setCat] = useState("");
  const [payer, setPayer] = useState("");
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(empty(me.id));
  const [editId, setEditId] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const q = new URLSearchParams({ month, ...(cat ? { category: cat } : {}), ...(payer ? { paid_by: payer } : {}) });
    try { setRows(await api(`/households/${hid}/expenses?${q}`)); } catch (e) { setError(e.message); }
  }, [hid, month, cat, payer]);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault(); setError("");
    const body = { ...form, amount: parseFloat(form.amount), paid_by: Number(form.paid_by) };
    try {
      if (editId) await api(`/households/${hid}/expenses/${editId}`, { method: "PUT", body });
      else await api(`/households/${hid}/expenses`, { method: "POST", body });
      setForm(empty(me.id)); setEditId(null); setMonth(body.spent_on.slice(0, 7)); load(); refreshHousehold();
    } catch (err) { setError(err.message); }
  };
  const del = async (r) => {
    try { await api(`/households/${hid}/expenses/${r.id}`, { method: "DELETE" }); load(); refreshHousehold(); } catch (e) { setError(e.message); }
  };
  const edit = (r) => { setEditId(r.id); setForm({ amount: r.amount, category: r.category, spent_on: r.spent_on, note: r.note, shared: r.shared, paid_by: r.paid_by }); };
  const canChange = (r) => !r.dataset_record && (household.my_role === "owner" || (household.my_role === "member" && r.created_by === me.id));
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="wrap">
      <header className="page"><div><div className="eyebrow">Tracking</div><h1>Expenses</h1>
        <div className="sub">Everything the household spends. Forecasts use these amounts by category and month.</div></div></header>
      <ErrorBox error={error} />
      {canWrite && (
        <form className="card" onSubmit={submit}>
          <h3>{editId ? "Edit expense" : "Add expense"}</h3>
          <div className="row">
            <label className="field" htmlFor="amount">Amount ({cur})<input id="amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={set("amount")} required style={{ width: 140 }} /></label>
            <label className="field" htmlFor="category">Category<select id="category" value={form.category} onChange={set("category")}>
              {household.categories.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field" htmlFor="spent_on">Date<input id="spent_on" type="date" value={form.spent_on} onChange={set("spent_on")} required /></label>
            <label className="field" htmlFor="paid_by">Paid by<select id="paid_by" value={form.paid_by} onChange={set("paid_by")}>
              {household.members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}</select></label>
            <label className="field" htmlFor="note" style={{ flex: 1, minWidth: 160 }}>Note<input id="note" value={form.note} maxLength={200} onChange={set("note")} placeholder="optional" /></label>
            <label className="planedit" htmlFor="shared"><input id="shared" type="checkbox" checked={form.shared} onChange={set("shared")} /> Shared</label>
          </div>
          <div className="row">
            <button className="primary">{editId ? "Save changes" : "Add expense"}</button>
            {editId && <button type="button" onClick={() => { setEditId(null); setForm(empty(me.id)); }}>Cancel</button>}
          </div>
        </form>
      )}
      <div className="bar">
        <div className="stepper">
          <button aria-label="Previous month" onClick={() => setMonth(monthAdd(month, -1))}>←</button>
          <div className="month">{monthLabel(month)}</div>
          <button aria-label="Next month" onClick={() => setMonth(monthAdd(month, 1))}>→</button>
        </div>
        <div className="row">
          <select aria-label="Filter by category" value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">All categories</option>{household.categories.map((c) => <option key={c}>{c}</option>)}</select>
          <select aria-label="Filter by member" value={payer} onChange={(e) => setPayer(e.target.value)}>
            <option value="">All members</option>{household.members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}</select>
        </div>
      </div>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Date</th><th>Category</th><th>Note</th><th>Paid by</th><th>Type</th><th style={{ textAlign: "right" }}>Amount</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="num">{r.spent_on}</td><td>{r.category}</td><td>{r.note}</td><td>{r.paid_by_name}</td>
                <td><span className="sub">{r.dataset_record ? "Dataset" : r.shared ? "Shared" : "Personal"}</span></td>
                <td className="amt">{money(r.amount, cur)}</td>
                <td style={{ whiteSpace: "nowrap" }}>{canChange(r) && <><button className="small" onClick={() => edit(r)}>Edit</button> <button className="small danger" onClick={() => del(r)}>Delete</button></>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={7} className="sub">No expenses for {monthLabel(month)}.</td></tr>}
          </tbody>
          {rows.length > 0 && <tfoot><tr><td colSpan={5}><b>Total</b></td><td className="amt"><b>{money(total, cur)}</b></td><td /></tr></tfoot>}
        </table>
      </div>
    </div>
  );
}
