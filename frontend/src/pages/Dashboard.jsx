import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, memberColor, money, monthLabel, pct, statusColor, thisMonth } from "../api.js";
// Dashboard shows the latest completed month with data; the forecast is for the month after it.
import { useApp } from "../App.jsx";
import { ErrorBox, Meter } from "../components/ui.jsx";

export default function Dashboard() {
  const { household, hid } = useApp();
  const month = household.data_source === "bls" ? household.latest_month : thisMonth();
  const fcMonth = household.forecast_month;
  const [sum, setSum] = useState(null);
  const [fc, setFc] = useState(null);
  const [acts, setActs] = useState([]);
  const [error, setError] = useState("");
  const cur = household.currency;

  useEffect(() => {
    (async () => {
      try {
        const [s, a] = await Promise.all([api(`/households/${hid}/summary/${month}`), api(`/households/${hid}/activity?limit=6`)]);
        setSum(s); setActs(a);
        setFc(await api(`/households/${hid}/forecast/${fcMonth}`));
      } catch (e) { setError(e.message); }
    })();
  }, [hid, month, fcMonth]);

  const flagged = fc?.categories.filter((c) => c.status === "over") || [];
  return (
    <div className="wrap">
      <header className="page">
        <div><div className="eyebrow">{monthLabel(month)}</div><h1>{household.name}</h1>
          <div className="sub">Your role: {household.my_role}</div></div>
        <div className="row">{household.data_source !== "bls" && <Link className="btn" to="/expenses">+ Add expense</Link>}<Link className="btn" to="/forecast">Open forecast →</Link></div>
      </header>
      <ErrorBox error={error} />
      {sum && (
        <div className="summary">
          <div className="sum"><div className="eyebrow">Spent in {monthLabel(month)}</div><div className="v">{money(sum.spent_total, cur)}</div></div>
          <div className="sum"><div className="eyebrow">Shared plan</div><div className="v">{money(sum.plan_total, cur)}</div>
            <div className="small-muted">{sum.agreement.final ? "Agreed by all members" : `${sum.agreement.agreed_count} of ${sum.agreement.voters} agreed`}</div></div>
          <div className="sum"><div className="eyebrow">AI forecast for {monthLabel(fcMonth)}</div><div className="v">{fc ? money(fc.total, cur) : "…"}</div>
            {fc?.total && fc.plan_total ? <div className="small-muted">{pct(((fc.total - fc.plan_total) / fc.plan_total) * 100)} vs plan</div> : null}</div>
        </div>
      )}
      <div className="grid">
        <div className="card">
          <h3>Spending vs plan, {monthLabel(month)}</h3>
          {sum && Object.keys(sum.plans).map((c) => {
            const p = sum.plans[c].amount, s = sum.spent[c];
            const st = !p ? "none" : s > p ? "over" : s > 0.9 * p ? "ok" : "under";
            return (
              <div key={c} className="list" style={{ gap: 4 }}>
                <div className="card-head"><span>{c}</span><span className="small-muted"><b>{money(s, cur)}</b> / {money(p, cur)}</span></div>
                <Meter value={s} plan={p} color={statusColor(st === "under" ? "ok" : st)} />
              </div>
            );
          })}
        </div>
        <div className="list" style={{ gap: 12 }}>
          <div className="card">
            <h3>Needs attention in {monthLabel(fcMonth)}</h3>
            {!fc ? <p className="sub">Calculating forecast…</p> : flagged.length === 0 ? <p className="sub">No category is forecast to go more than 5% over plan.</p> :
              flagged.map((c) => (
                <div key={c.category} className="card-head">
                  <span>{c.category}</span>
                  <span className="chip over">Forecast {money(c.forecast, cur)} · {pct(c.vs_plan_pct)}</span>
                </div>
              ))}
            <Link to="/forecast">See recommendations →</Link>
          </div>
          <div className="card">
            <h3>Who paid in {monthLabel(month)}</h3>
            {sum?.by_member.length ? sum.by_member.map((m, i) => (
              <div key={m.user_id ?? i} className="card-head">
                <span className="member" style={{ border: 0, padding: 0 }}><span className="av" style={{ background: memberColor(i) }}>{m.name[0]}</span>{m.name}</span>
                <span className="small-muted"><b>{money(m.amount, cur)}</b></span>
              </div>
            )) : <p className="sub">No expenses this month yet.</p>}
          </div>
          <div className="card">
            <h3>Recent activity</h3>
            {acts.map((a) => <div key={a.id} className="sub">{a.action}</div>)}
            <Link to="/activity">Full activity log →</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
