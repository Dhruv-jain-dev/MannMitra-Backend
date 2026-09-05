import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

export default function Layout({ user, onLogout, mobileOpen, setMobileOpen }) {
  return <div className="dashboard-shell"><Sidebar user={user} open={mobileOpen} onClose={() => setMobileOpen(false)} onLogout={onLogout} /><div className="dashboard-main"><Navbar user={user} onLogout={onLogout} onMenu={() => setMobileOpen(true)} /><main className="page-wrap"><Outlet /></main></div></div>;
}
