import { Activity, ArrowRight, HeartHandshake, MessageCircle, ShieldCheck, Sparkles, Wind } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { moods } from "../data";
import PageTitle from "../components/PageTitle";
import CounselorConnect from "../components/CounselorConnect";
import PrivacyNote from "../components/PrivacyNote";
import { submitCheckIn } from "../services/wellbeing";

export default function StudentDashboard({ user }) {
  const [mood, setMood] = useState(null);
  const [stress, setStress] = useState(4);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const saveCheckIn = async () => {
    if (!mood || status === "saving") return;
    setStatus("saving"); setError("");
    try { await submitCheckIn({ mood, stress_level: Number(stress), notes: null }); setStatus("success"); window.dispatchEvent(new Event("campuspulse:checkin-saved")); }
    catch (requestError) { setStatus("error"); setError(requestError.response?.data?.detail || requestError.message || "Unable to save your check-in."); }
  };
  return <>
    <PageTitle eyebrow="STUDENT WELLBEING" title={`Welcome back, ${user?.name || "Student"}.`} subtitle="A calm space to check in, talk to MannMitra, use a wellness activity, or reach human support." action={<div className="mini-user"><div className="avatar">{(user?.name || "S").slice(0,1)}</div><span>{user?.department || "Student"}</span></div>} />
    <div className="student-signal card"><div className="signal-icon"><ShieldCheck size={18} /></div><div><b>Your wellbeing space</b><p>Your check-ins stay separate from institutional analytics. Production decisions should use appropriate consent, access controls and human review.</p></div><span className="privacy-tag">DPDP ACT ALIGNED</span></div>
    <div className="overview-grid">
      <div className="card checkin-card"><div className="card-top"><div><span className="eyebrow">DAILY CHECK-IN</span><h2>How are you feeling today?</h2></div><Activity size={18} /></div><p>A tiny check-in can help you notice patterns without turning wellbeing into a task.</p><div className="mood-row">{moods.map(m => <button type="button" className={`mood-btn ${mood === m.id ? "selected" : ""}`} key={m.id} onClick={() => { setMood(m.id); setStatus("idle"); }}><span>{m.icon}</span>{m.label}</button>)}</div><div className="range-label"><span>Stress level</span><b>{stress}/10</b></div><input className="stress-range" type="range" min="0" max="10" value={stress} onChange={e => { setStress(e.target.value); setStatus("idle"); }} /><button type="button" className="btn btn-primary" onClick={saveCheckIn} disabled={!mood || status === "saving"}>{status === "saving" ? "Saving…" : "Save check-in"} <ArrowRight size={15} /></button>{status === "success" && <p className="small-muted">Check-in saved.</p>}{status === "error" && <p className="small-muted">{error}</p>}</div>
      <div className="card companion-card"><div className="card-top"><div><span className="eyebrow">MANNMITRA</span><h2>Talk it out.</h2></div><MessageCircle size={18} /></div><p>Use the companion for a private-feeling conversation. The backend can return text, risk and RAG-grounded support later.</p><div className="orb-wrap"><div className="orb"><Sparkles size={24} /></div></div><button className="btn btn-soft full" onClick={() => window.location.assign("/app/mannmitra")}>Open MannMitra <ArrowRight size={15} /></button></div>
    </div>
    <div className="quick-grid"><Quick title="Wellness Zone" text="Six short activities: breathing, focus, memory, color calm, mood garden and meditation." icon={<Wind />} href="/app/wellness" /><Quick title="My Insights" text="See supportive patterns from your check-ins without exposing them publicly." icon={<Activity />} href="/app/insights" /><Quick title="Anonymous counselor support" text="Start a pseudonymous two-way support conversation with a counselor." icon={<HeartHandshake />} href="/app/anonymous-support" /></div>
    <div id="support"><CounselorConnect /></div>
    <PrivacyNote>Frontend is designed around consent, purpose limitation, role-based access and minimal exposure. Legal compliance depends on the connected production policies and backend controls.</PrivacyNote>
  </>;
}

function Quick({ title, text, icon, href }) { return href.startsWith("#") ? <a className="quick-card card" href={href}><div className="feature-icon">{icon}</div><div><h3>{title}</h3><p>{text}</p></div><ArrowRight size={15} /></a> : <Link className="quick-card card" to={href}><div className="feature-icon">{icon}</div><div><h3>{title}</h3><p>{text}</p></div><ArrowRight size={15} /></Link>; }
