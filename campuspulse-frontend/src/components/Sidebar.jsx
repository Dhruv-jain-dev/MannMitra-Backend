import { Activity, BarChart3, Brain, CheckCircle2, Gamepad2, HeartHandshake, Home, LogOut, MessageCircle, ShieldCheck, Users, X, Zap } from "lucide-react";
import { NavLink } from "react-router-dom";
import Brand from "./Brand";

const studentItems = [
  ["/app/overview", "Overview", Home], ["/app/mannmitra", "MannMitra", MessageCircle], ["/app/checkin", "Daily Check-in", CheckCircle2], ["/app/wellness", "Wellness Zone", Gamepad2], ["/app/insights", "My Insights", BarChart3]
];
const counselorItems = [
  ["/app/counselor", "Command Overview", Home], ["/app/counselor/messages", "Priority Cases", Zap], ["/app/counselor/interventions", "Interventions", HeartHandshake], ["/app/counselor/followups", "Follow-ups Due", CheckCircle2], ["/app/counselor/analytics", "Campus Analytics", BarChart3]
];
const adminItems = [
  ["/app/admin", "Campus Overview", Home], ["/app/admin/departments", "Department Trends", Activity], ["/app/admin/forecast", "Stress Forecasting", BarChart3], ["/app/admin/governance", "Data Governance", ShieldCheck]
];

export default function Sidebar({ user, open, onClose, onLogout }) {
  const role = user?.role || "student";
  const items = role === "counselor" ? counselorItems : role === "admin" ? adminItems : studentItems;
  const label = role === "counselor" ? "CAMPUS PULSE (COUNSELOR)" : role === "admin" ? "CAMPUS PULSE (ADMIN)" : "CAMPUS PULSE (STUDENT)";

  return (
    <>
      {open && <button className="sidebar-overlay" onClick={onClose} aria-label="Close navigation" />}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="side-brand"><Brand /><button className="mobile-close icon-btn" onClick={onClose}><X size={16} /></button></div>
        <div className="portal-label">{label}</div>
        <nav>
          {items.map(([to, text, Icon]) => <NavLink key={to} to={to} onClick={onClose} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon size={15} /><span>{text}</span></NavLink>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-side"><ShieldCheck size={15} /><span>DPDP Act-aligned privacy design</span></div>
          <button className="nav-link danger" onClick={() => { onLogout(); onClose(); }}><LogOut size={15} /><span>Sign out</span></button>
        </div>
      </aside>
    </>
  );
}
