import { ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { moods } from "../data";
import PageTitle from "../components/PageTitle";

export default function CheckIn() {
  const [mood, setMood] = useState(""); const [stress, setStress] = useState(5); const [done, setDone] = useState(false);
  return <><PageTitle eyebrow="DAILY CHECK-IN" title="A minute to notice where you are." subtitle="This prototype captures the fields your backend can later score and classify." /><div className="checkin-page-grid"><div className="card large-checkin"><span className="eyebrow">STEP 01</span><h2>How are you feeling?</h2><div className="large-mood-grid">{moods.map(m => <button key={m.id} className={`large-mood ${mood === m.id ? "selected" : ""}`} onClick={() => setMood(m.id)}><span>{m.icon}</span><b>{m.label}</b><small>signal {m.score}/4</small></button>)}</div><span className="eyebrow">STEP 02</span><h2>How stressed do you feel?</h2><div className="stress-big"><strong>{stress}</strong><span>/10</span></div><input className="stress-range" type="range" min="0" max="10" value={stress} onChange={e => setStress(e.target.value)} /><button className="btn btn-primary" onClick={() => setDone(true)} disabled={!mood}>Complete check-in <ArrowRight size={15}/></button>{done && <div className="checkin-success"><CheckCircle2 size={18}/> Check-in saved in demo mode. Backend can replace this with real classification.</div>}</div><div className="card checkin-side"><ShieldCheck size={20}/><h3>Privacy by design</h3><p>Collect only what is needed for the stated wellbeing purpose. Production storage, consent and access controls belong in the backend.</p></div></div></>;
}
