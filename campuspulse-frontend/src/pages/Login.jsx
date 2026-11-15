import { ArrowRight, HeartHandshake, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Brand from "../components/Brand";
import { authenticateUser, clearUser, getCurrentProfile, requestPasswordReset } from "../services/auth";

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  const submit = async e => { e.preventDefault(); setLoading(true); setAuthError(""); try { await authenticateUser(email, password); const profile = await getCurrentProfile(); onLogin(profile); navigate(profile.must_change_password ? "/change-password" : profile.role === "student" ? "/app/overview" : profile.role === "counselor" ? "/app/counselor" : "/app/admin"); } catch (error) { await clearUser(); setAuthError(error.message); } finally { setLoading(false); } };
  const recover = async () => { if (!email) { setAuthError("Enter your email address first."); return; } try { await requestPasswordReset(email); setAuthError("Password recovery instructions were sent if the account exists."); } catch (error) { setAuthError(error.message); } };

  return <div className="auth-page"><header className="topbar"><Brand /><button className="btn btn-ghost" onClick={() => navigate("/")}>← Back</button></header><div className="auth-card">
    <div className="auth-head"><div className="auth-icon"><ShieldCheck /></div><span className="status-dot">SECURE SIGN-IN</span><h1>Welcome back</h1><p>Choose your portal and continue to CampusPulse.</p></div>
    <form onSubmit={submit}><label>Campus email<input value={email} onChange={e => setEmail(e.target.value)} type="email" required placeholder="you@campus.edu" /></label><label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password" required placeholder="••••••••" /></label><div className="form-row"><label className="check"><input type="checkbox" defaultChecked /> Keep me signed in</label><button type="button" className="link-btn" onClick={recover}>Forgot password?</button></div>{authError && <div className="small-muted">{authError}</div>}<button className="btn btn-primary full" disabled={loading}>{loading ? "Signing in…" : "Sign in"} <ArrowRight size={17} /></button></form>
    <p className="auth-switch">Don't have an account? <button onClick={() => navigate("/signup")} className="link-btn">Create one</button></p><div className="secure-note"><HeartHandshake size={15} /> {import.meta.env.VITE_LOCAL_TEST_AUTH === "true" ? "Isolated local test authentication." : "Secure authentication by Supabase Auth."}</div>
  </div></div>;
}
