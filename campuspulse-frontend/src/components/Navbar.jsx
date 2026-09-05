import { LogOut, Menu, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import Brand from "./Brand";

export default function Navbar({ user, onLogout, onMenu }) {
  const navigate = useNavigate();
  const roleLabel = user?.role === "counselor" ? "Counselor Center" : user?.role === "admin" ? "Campus Admin" : "Student Portal";

  return (
    <header className="topbar app-navbar">
      <div className="nav-left">
        <button className="mobile-menu icon-btn" onClick={onMenu} aria-label="Open navigation"><Menu size={18} /></button>
        <Brand compact />
        <span className="role-chip"><ShieldCheck size={12} /> {roleLabel}</span>
      </div>
      <div className="top-actions">
        <span className="privacy-pill"><ShieldCheck size={13} /> Privacy-first</span>
        <div className="nav-user"><div className="avatar">{(user?.name || "S").slice(0,1)}</div><span>{user?.name || "Student"}</span></div>
        <button className="icon-btn" onClick={() => { onLogout(); navigate("/"); }} aria-label="Sign out"><LogOut size={16} /></button>
      </div>
    </header>
  );
}
