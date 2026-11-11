import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox } from "../components/ui.jsx";

export default function Activity() {
  const { hid } = useApp();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => { api(`/households/${hid}/activity?limit=300`).then(setRows).catch((e) => setError(e.message)); }, [hid]);
  return (
    <div className="wrap" style={{ maxWidth: 820 }}>
      <header className="page"><div><div className="eyebrow">Transparency</div><h1>Activity log</h1>
        <div className="sub">Every change to expenses, plans, roles and members, visible to everyone in the household.</div></div></header>
      <ErrorBox error={error} />
      <div className="card">
        {rows.map((a) => (
          <div className="act" key={a.id}><span>{a.action}</span><time dateTime={a.at}>{new Date(a.at).toLocaleString()}</time></div>
        ))}
        {rows.length === 0 && <p className="sub">No activity yet.</p>}
      </div>
    </div>
  );
}
