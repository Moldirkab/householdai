import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api, setToken } from "../api.js";
import { useApp } from "../App.jsx";
import { ErrorBox } from "../components/ui.jsx";

function AuthForm({ mode }) {
  const { refreshMe } = useApp();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", body: form });
      setToken(r.token);
      await refreshMe();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="auth">
      <div className="card">
        <div>
          <div className="eyebrow">Shared household budget</div>
          <h1>{mode === "login" ? "Log in" : "Create an account"}</h1>
          <p className="sub">Track shared expenses, plan a monthly budget together and get AI forecasts for next month.</p>
        </div>
        <ErrorBox error={error} />
        <form onSubmit={submit} className="list">
          {mode === "register" && (
            <label className="field" htmlFor="name">Name<input id="name" value={form.name} onChange={set("name")} required /></label>
          )}
          <label className="field" htmlFor="email">Email<input id="email" type="email" value={form.email} onChange={set("email")} required /></label>
          <label className="field" htmlFor="password">Password
            <input id="password" type="password" minLength={6} value={form.password} onChange={set("password")} required /></label>
          <button className="primary" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}</button>
        </form>
        {mode === "login" ? (
          <>
            <p className="sub">No account? <Link to="/register">Create one</Link></p>
            <div className="note"><b>Demo household (real BLS data):</b> log in as <span className="num">g1.demo@demo.kz</span> with password <span className="num">demo1234</span>, or create your own account and join with invite code <span className="num">DEMOG1</span>.</div>
          </>
        ) : <p className="sub">Already have an account? <Link to="/login">Log in</Link></p>}
      </div>
    </div>
  );
}

export const Login = () => <AuthForm mode="login" />;
export const Register = () => <AuthForm mode="register" />;
