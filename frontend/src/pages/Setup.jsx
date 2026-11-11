import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox } from "../components/ui.jsx";

export default function Setup() {
  const { refreshMe, setHid } = useApp();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("₸");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const done = async (id) => { await refreshMe(); setHid(id); nav("/"); };
  const create = async (e) => {
    e.preventDefault(); setError("");
    try { done((await api("/households", { method: "POST", body: { name, currency } })).id); } catch (err) { setError(err.message); }
  };
  const join = async (e) => {
    e.preventDefault(); setError("");
    try { done((await api("/households/join", { method: "POST", body: { invite_code: code } })).id); } catch (err) { setError(err.message); }
  };

  return (
    <div className="wrap" style={{ maxWidth: 760 }}>
      <header className="page"><div><div className="eyebrow">Get started</div><h1>Create or join a household</h1>
        <div className="sub">A household is a shared budget for people who live or spend together.</div></div></header>
      <ErrorBox error={error} />
      <div className="grid">
        <form className="card" onSubmit={create}>
          <h3>Create a household</h3>
          <label className="field" htmlFor="hname">Name<input id="hname" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Our flat" required /></label>
          <label className="field" htmlFor="hcur">Currency
            <select id="hcur" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="₸">₸ Tenge</option><option value="$">$ US dollar</option><option value="€">€ Euro</option><option value="₽">₽ Ruble</option>
            </select></label>
          <button className="primary">Create</button>
          <p className="sub">You become the owner and can invite others with a code.</p>
        </form>
        <form className="card" onSubmit={join}>
          <h3>Join with an invite code</h3>
          <label className="field" htmlFor="code">Invite code<input id="code" className="num" value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 3F9A1C" required /></label>
          <button className="primary">Join</button>
          <p className="sub">Ask the household owner for the code (Household page).</p>
        </form>
      </div>
    </div>
  );
}
