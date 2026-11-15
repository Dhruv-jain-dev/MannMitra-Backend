import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { updatePassword } from "../services/auth";

export default function ChangePassword({ onComplete }) {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const strong = password.length >= 12 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password);
  const submit = async event => {
    event.preventDefault(); setError("");
    if (!strong) { setError("Use at least 12 characters with uppercase, lowercase, number and symbol."); return; }
    if (password !== confirmation) { setError("Passwords do not match."); return; }
    setSaving(true);
    try { const profile = await updatePassword(password); onComplete(profile); navigate(profile.role === "admin" ? "/app/admin" : profile.role === "counselor" ? "/app/counselor" : "/app", { replace: true }); }
    catch (e) { setError(e.message || "The password could not be changed."); }
    finally { setSaving(false); }
  };
  return <main className="auth-page"><section className="auth-card"><div className="auth-head"><div className="auth-icon"><ShieldCheck size={22}/></div><span className="eyebrow">FIRST LOGIN SECURITY</span><h1>Set a new password</h1><p>Your temporary password must be replaced before you can access MannMitra.</p></div><form onSubmit={submit}><label>New password<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="new-password" required /></label><label>Confirm new password<input type="password" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="new-password" required /></label><p className="small-muted">At least 12 characters, including uppercase, lowercase, a number and a symbol.</p>{error && <div className="small-muted">{error}</div>}<button className="btn btn-primary full" disabled={saving}>{saving ? "Updating…" : "Update password"}</button></form></section></main>;
}
