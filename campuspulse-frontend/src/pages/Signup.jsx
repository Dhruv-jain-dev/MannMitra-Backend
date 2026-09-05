import { HeartHandshake } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Brand from "../components/Brand";
import { authenticateDevelopmentUser } from "../services/auth";

export default function Signup({ onLogin }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", department: "Computer Science", year: "3rd Year", password: "" });
  const [authError, setAuthError] = useState("");
  const update = (key, value) => setForm(v => ({ ...v, [key]: value }));
  const submit = async e => { e.preventDefault(); setAuthError(""); try { const user = await authenticateDevelopmentUser({ ...form, role: "student" }); onLogin(user); navigate("/app/overview"); } catch (error) { setAuthError(error.message); } };
  return <div className="auth-page"><header className="topbar"><Brand /><button className="btn btn-ghost" onClick={() => navigate("/login")}>← Sign in</button></header><div className="auth-card signup-card">
    <div className="auth-head"><div className="auth-icon"><HeartHandshake /></div><span className="status-dot">STUDENT PORTAL</span><h1>Create your space</h1><p>A private account for your wellbeing journey.</p></div>
    <form onSubmit={submit} className="two-col-form"><label>Full name<input required value={form.name} onChange={e => update("name", e.target.value)} placeholder="Your name" /></label><label>Campus email<input required type="email" value={form.email} onChange={e => update("email", e.target.value)} placeholder="you@campus.edu" /></label><label>Department<select value={form.department} onChange={e => update("department", e.target.value)}><option>Computer Science</option><option>Electronics</option><option>Mechanical</option><option>Management</option><option>Other</option></select></label><label>Year<select value={form.year} onChange={e => update("year", e.target.value)}><option>1st Year</option><option>2nd Year</option><option>3rd Year</option><option>4th Year</option></select></label><label className="span-2">Password<input required type="password" value={form.password} onChange={e => update("password", e.target.value)} placeholder="Create a password" /></label><div className="span-2 consent-box"><input type="checkbox" required /> <span>I understand that wellbeing information should be collected and used only for stated purposes, with appropriate consent and protection.</span></div>{authError && <div className="small-muted span-2">{authError}</div>}<button className="btn btn-primary full span-2">Create student account</button></form>
  </div></div>;
}
