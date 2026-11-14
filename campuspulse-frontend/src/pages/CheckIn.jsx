import { ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { moods } from "../data";
import PageTitle from "../components/PageTitle";
import { submitCheckIn } from "../services/wellbeing";

export default function CheckIn() {
  const [mood, setMood] = useState("");
  const [stress, setStress] = useState(5);
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const saveCheckIn = async () => {
    if (!mood || status === "saving") return;
    setStatus("saving");
    setError("");
    try {
      await submitCheckIn({ mood, stress_level: Number(stress), notes: notes.trim() || null });
      setStatus("success");
      window.dispatchEvent(new Event("campuspulse:checkin-saved"));
    } catch (requestError) {
      setStatus("error");
      setError(requestError.response?.data?.detail || requestError.message || "Unable to save your check-in.");
    }
  };

  return <><PageTitle eyebrow="DAILY CHECK-IN" title="A minute to notice where you are." subtitle="Your check-in is saved privately and used only for your personal wellbeing patterns." /><div className="checkin-page-grid"><div className="card large-checkin"><span className="eyebrow">STEP 01</span><h2>How are you feeling?</h2><div className="large-mood-grid">{moods.map(m => <button type="button" key={m.id} className={`large-mood ${mood === m.id ? "selected" : ""}`} onClick={() => { setMood(m.id); setStatus("idle"); }}><span>{m.icon}</span><b>{m.label}</b><small>signal {m.score}/4</small></button>)}</div><span className="eyebrow">STEP 02</span><h2>How stressed do you feel?</h2><div className="stress-big"><strong>{stress}</strong><span>/10</span></div><input className="stress-range" type="range" min="0" max="10" value={stress} onChange={e => { setStress(e.target.value); setStatus("idle"); }} /><label className="checkin-notes">Optional note<textarea value={notes} onChange={e => setNotes(e.target.value)} maxLength={2000} rows={3} placeholder="Anything you want to remember about today?" /></label><button type="button" className="btn btn-primary" onClick={saveCheckIn} disabled={!mood || status === "saving"}>{status === "saving" ? "Saving…" : "Complete check-in"} <ArrowRight size={15}/></button>{status === "success" && <div className="checkin-success"><CheckCircle2 size={18}/> Check-in saved. Your personal insights will refresh with this entry.</div>}{status === "error" && <div className="small-muted">{error}</div>}</div><div className="card checkin-side"><ShieldCheck size={20}/><h3>Privacy by design</h3><p>Collect only what is needed for the stated wellbeing purpose. Your records are scoped to your signed-in student account.</p></div></div></>;
}
