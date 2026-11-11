import React from "react";
import { memberColor } from "../api.js";

export function Meter({ value, plan, color }) {
  const max = Math.max(value || 0, plan || 0) * 1.15 || 1;
  return (
    <div className="meter" title="Bar = amount, line = plan">
      <div className="fill" style={{ width: `${((value || 0) / max) * 100}%`, background: color }} />
      {plan ? <div className="plan" style={{ left: `${(plan / max) * 100}%` }} /> : null}
    </div>
  );
}

// Member pills with "agrees" checkboxes (same as the questionnaire demo). Only your own checkbox is clickable.
export function MemberPills({ agreement, meId, canAgree, onToggle }) {
  if (!agreement) return null;
  return (
    <div className="members">
      {agreement.members.map((m, i) => {
        const voter = m.role !== "viewer";
        const mine = m.user_id === meId;
        return (
          <label className="member" key={m.user_id} htmlFor={`agree-${m.user_id}`}>
            <span className="av" style={{ background: memberColor(i) }}>{m.name[0]}</span>
            {m.name}{mine ? " (you)" : ""}
            {voter ? (
              <>
                <input id={`agree-${m.user_id}`} type="checkbox" checked={m.agreed}
                  disabled={!mine || !canAgree} onChange={(e) => onToggle(e.target.checked)}
                  aria-label={`${m.name} agrees with the plan`} /> agrees
              </>
            ) : <span className="sub">viewer</span>}
          </label>
        );
      })}
    </div>
  );
}

export function ErrorBox({ error }) {
  return error ? <div className="error" role="alert">{error}</div> : null;
}
