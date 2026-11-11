import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { HashRouter, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "./api.js";
import { Login, Register } from "./pages/Auth.jsx";
import Setup from "./pages/Setup.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Expenses from "./pages/Expenses.jsx";
import Budget from "./pages/Budget.jsx";
import Forecast from "./pages/Forecast.jsx";
import Activity from "./pages/Activity.jsx";
import HouseholdPage from "./pages/Household.jsx";

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);
const HKEY = "householdai_household";

export default function App() {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(!!getToken());
  const [hid, setHidState] = useState(() => Number(localStorage.getItem(HKEY)) || null);
  const [household, setHousehold] = useState(null);

  const setHid = (id) => { setHidState(id); id ? localStorage.setItem(HKEY, id) : localStorage.removeItem(HKEY); };

  const refreshMe = useCallback(async () => {
    if (!getToken()) { setMe(null); setLoading(false); return null; }
    try {
      const u = await api("/me");
      setMe(u);
      if (!u.households.find((h) => h.id === hid)) setHid(u.households[0]?.id || null);
      return u;
    } catch { setToken(null); setMe(null); return null; }
    finally { setLoading(false); }
  }, [hid]);

  const refreshHousehold = useCallback(async () => {
    if (!hid || !getToken()) { setHousehold(null); return; }
    try { setHousehold(await api(`/households/${hid}`)); } catch { setHousehold(null); }
  }, [hid]);

  useEffect(() => { refreshMe(); }, []);  // eslint-disable-line
  useEffect(() => { refreshHousehold(); }, [hid, me?.id]);  // eslint-disable-line

  const value = { me, setMe, refreshMe, hid, setHid, household, refreshHousehold };
  if (loading) return <div className="wrap"><p className="sub">Loading…</p></div>;
  return (
    <Ctx.Provider value={value}>
      <HashRouter>
        <Routes>
          <Route path="/login" element={me ? <Navigate to="/" /> : <Login />} />
          <Route path="/register" element={me ? <Navigate to="/" /> : <Register />} />
          <Route path="/setup" element={me ? <Shell><Setup /></Shell> : <Navigate to="/login" />} />
          <Route path="/*" element={!me ? <Navigate to="/login" /> : !hid ? <Navigate to="/setup" /> : <Shell><Main /></Shell>} />
        </Routes>
      </HashRouter>
    </Ctx.Provider>
  );
}

function Main() {
  const { household } = useApp();
  if (!household) return <div className="wrap"><p className="sub">Loading household…</p></div>;
  return (
    <>
    {household.data_source === "bls" && (
      <div className="wrap" style={{ paddingBottom: 0 }}>
        <div className="note" role="note"><b>Demo household with real research data.</b> All expenses are the real BLS Consumer
          Expenditure Survey values from the research dataset: weighted average monthly spending per U.S. household,
          {" "}{household.first_month} to {household.latest_month}, in USD. They are not the personal spending of anyone in this
          household and cannot be edited. Create your own household to track your own expenses.</div>
      </div>
    )}
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/expenses" element={<Expenses />} />
      <Route path="/budget" element={<Budget />} />
      <Route path="/forecast" element={<Forecast />} />
      <Route path="/activity" element={<Activity />} />
      <Route path="/household" element={<HouseholdPage />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
    </>
  );
}

function Shell({ children }) {
  const { me, hid, setHid, setMe } = useApp();
  const nav = useNavigate();
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    setToken(null); setMe(null); nav("/login");
  };
  return (
    <>
      <div className="topbar">
        <div className="topbar-in">
          <div className="brand"><span className="dot" />HouseholdAI</div>
          {hid ? (
            <nav className="tabs">
              <NavLink to="/" end>Dashboard</NavLink>
              <NavLink to="/expenses">Expenses</NavLink>
              <NavLink to="/budget">Budget</NavLink>
              <NavLink to="/forecast">Forecast</NavLink>
              <NavLink to="/activity">Activity</NavLink>
              <NavLink to="/household">Household</NavLink>
            </nav>
          ) : <span />}
          <div className="userbox">
            {me?.households?.length > 0 && (
              <select id="household-switch" aria-label="Household" value={hid || ""} onChange={(e) => {
                if (e.target.value === "new") nav("/setup"); else { setHid(Number(e.target.value)); nav("/"); }
              }}>
                {me.households.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
                <option value="new">+ Create or join…</option>
              </select>
            )}
            <span className="sub">{me?.name}</span>
            <button className="small" onClick={logout}>Log out</button>
          </div>
        </div>
      </div>
      {children}
    </>
  );
}
