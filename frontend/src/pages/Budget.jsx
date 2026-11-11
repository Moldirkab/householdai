import React, { useCallback, useEffect, useState } from "react";
import { api, money, monthAdd, monthLabel, statusColor } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox, MemberPills, Meter } from "../components/ui.jsx";

export default function Budget() {
  const { me, household, hid } = useApp();
  const cur = household.currency;
  const canEdit = household.my_role !== "viewer";
  const [month, setMonth] = useState(household.forecast_month);
  const [b, setB] = useState(null);
  const [draft, setDraft] = useState({});
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api(`/households/${hid}/budgets/${month}`);
      setB(r);
      setDraft(Object.fromEntries(Object.entries(r.plans).map(([c, p]) => [c, p.amount ?? ""])));
    } catch (e) { setError(e.message); }
  }, [hid, month]);
  useEffect(() => { load(); setSaved(""); }, [load]);

  const save = async () => {
    setError("");
    const amounts = Object.fromEntries(Object.entries(draft).filter(([, v]) => v !== "").map(([c, v]) => [c, parseFloat(v)]));
    try { const r = await api(`/households/${hid}/budgets/${month}`, { method: "PUT", body: { amounts } }); setB(r); setSaved("Plan saved. Members need to agree again."); }
    catch (e) { setError(e.message); }
  };
  const agree = async (agreed) => {
    try { const a = await api(`/households/${hid}/agreement/${month}`, { method: "PUT", body: { agreed } }); setB({ ...b, agreement: a }); }
    catch (e) { setError(e.message); }
  };
  const planTotal = Object.values(draft).reduce((s, v) => s + (parseFloat(v) || 0), 0);
  const spentTotal = b ? Object.values(b.spent).reduce((s, v) => s + v, 0) : 0;

  return (
    <div className="wrap">
      <header className="page">
        <div><div className="eyebrow">Budgeting</div><h1>Shared plan</h1>
          <div className="sub">Set a monthly limit for each category together. The plan is final when every member agrees.</div></div>
        <MemberPills agreement={b?.agreement} meId={me.id} canAgree={canEdit} onToggle={agree} />
      </header>
      <div className="bar">
        <div className="stepper">
          <button aria-label="Previous month" onClick={() => setMonth(monthAdd(month, -1))}>←</button>
          <div className="month"><div className="eyebrow">Plan for</div>{monthLabel(month)}</div>
          <button aria-label="Next month" onClick={() => setMonth(monthAdd(month, 1))}>→</button>
        </div>
        {canEdit && <button className="primary" onClick={save}>Save plan</button>}
      </div>
      <ErrorBox error={error} />
      {saved && <div className="note">{saved}</div>}
      {b && (
        <>
          <div className="summary">
            <div className="sum"><div className="eyebrow">Plan total</div><div className="v">{money(planTotal, cur)}</div></div>
            <div className="sum"><div className="eyebrow">Spent so far</div><div className="v">{money(spentTotal, cur)}</div></div>
            <div className="sum"><div className="eyebrow">Left</div><div className="v" style={{ color: planTotal - spentTotal < 0 ? "var(--over)" : "var(--ok)" }}>{money(planTotal - spentTotal, cur)}</div></div>
          </div>
          <div className="grid">
            {Object.entries(b.plans).map(([c, p]) => {
              const plan = parseFloat(draft[c]) || 0, spent = b.spent[c];
              const st = !plan ? "none" : spent > plan ? "over" : "ok";
              return (
                <div className="card" key={c}>
                  <div className="card-head"><h3>{c}</h3>
                    <span className={`chip ${st}`}>{!plan ? "No plan" : spent > plan ? `Over by ${money(spent - plan, cur)}` : `${money(plan - spent, cur)} left`}</span></div>
                  <Meter value={spent} plan={plan} color={statusColor(st)} />
                  <div className="small-muted">Spent <b>{money(spent, cur)}</b> of {money(plan, cur)}</div>
                  <label className="planedit" htmlFor={`b-${c}`}>Monthly limit
                    <input id={`b-${c}`} type="number" min="0" step="10" value={draft[c]} disabled={!canEdit}
                      onChange={(e) => setDraft({ ...draft, [c]: e.target.value })} />
                    {p.suggested && p.amount !== null && <span className="chip none">suggested from last 3 months</span>}
                  </label>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
