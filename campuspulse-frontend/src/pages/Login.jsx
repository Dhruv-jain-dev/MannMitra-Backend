import { ArrowRight, HeartHandshake, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Brand from "../components/Brand";
import { authenticateDevelopmentUser, buildDemoProfile } from "../services/auth";

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const [role, setRole] = useState("student");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  const submit = async e => { e.preventDefault(); setLoading(true); setAuthError(""); try { const profile = await authenticateDevelopmentUser(buildDemoProfile(role, email)); onLogin(profile); navigate(role === "student" ? "/app/overview" : role === "counselor" ? "/app/counselor" : "/app/admin"); } catch (error) { setAuthError(error.message); } finally { setLoading(false); } };

  return <div className="auth-page"><header className="topbar"><Brand /><button className="btn btn-ghost" onClick={() => navigate("/")}>← Back</button></header><div className="auth-card">
    <div className="auth-head"><div className="auth-icon"><ShieldCheck /></div><span className="status-dot">SECURE SIGN-IN</span><h1>Welcome back</h1><p>Choose your portal and continue to CampusPulse.</p></div>
    <div className="role-tabs">{["student","counselor","admin"].map(r => <button type="button" key={r} className={role === r ? "active" : ""} onClick={() => setRole(r)}>{r === "student" ? "Student" : r === "counselor" ? "Counselor" : "Admin"}</button>)}</div>
    <form onSubmit={submit}><label>Campus email<input value={email} onChange={e => setEmail(e.target.value)} type="email" required placeholder="you@campus.edu" /></label><label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password" required placeholder="••••••••" /></label><div className="form-row"><label className="check"><input type="checkbox" defaultChecked /> Keep me signed in</label><button type="button" className="link-btn">Forgot password?</button></div>{authError && <div className="small-muted">{authError}</div>}<button className="btn btn-primary full" disabled={loading}>{loading ? "Signing in…" : `Sign in to ${role} portal`} <ArrowRight size={17} /></button></form>
    <p className="auth-switch">Don't have an account? <button onClick={() => navigate("/signup")} className="link-btn">Create one</button></p><div className="secure-note"><HeartHandshake size={15} /> Demo authentication only. Connect production auth through the backend.</div>
  </div></div>;
}
