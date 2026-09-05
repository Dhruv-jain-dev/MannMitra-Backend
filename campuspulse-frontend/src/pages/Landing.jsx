import { Activity, ArrowRight, MessageCircle, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import Brand from "../components/Brand";

export default function Landing() {
  const navigate = useNavigate();
  return <main className="landing">
    <header className="topbar landing-bar"><Brand /><div className="top-actions"><span className="privacy-pill"><ShieldCheck size={14} /> Privacy-first</span><button className="btn btn-ghost" onClick={() => navigate("/login")}>Sign in</button></div></header>
    <section className="hero">
      <div className="hero-badge">AI-POWERED STUDENT & CAMPUS WELLBEING</div>
      <h1>Nurturing minds,<br /><span>supporting growth.</span></h1>
      <p className="hero-copy">A calm, confidential space where MannMitra listens to students and CampusPulse helps connect the right support at the right time.</p>
      <div className="hero-actions"><button className="btn btn-primary btn-large" onClick={() => navigate("/login")}>Get started <ArrowRight size={18} /></button><button className="btn btn-soft" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>See how it works</button></div>
      <div className="feature-strip">
        <Feature icon={<MessageCircle />} title="MannMitra Companion" text="Text and voice-friendly wellbeing conversations." />
        <Feature icon={<Activity />} title="Early Intervention" text="Green, Yellow and Red support pathways." />
        <Feature icon={<ShieldCheck />} title="DPDP Act aligned" text="Consent-led, privacy-conscious experience." />
      </div>
    </section>
    <section className="landing-section" id="how"><div className="section-heading centered"><span className="eyebrow">THE CLOSED LOOP</span><h2>Check in. Understand. Support. Re-assess.</h2><p>Simple student interactions with clean API boundaries for the MannMitra backend, risk engine and future campus systems.</p></div><div className="loop-grid">{[["01","Student check-in","Mood and stress signals are captured through lightweight interactions."],["02","Risk classification","Backend signals can classify pathways as Green, Yellow or Red."],["03","Right support","Wellness activities or counselor connection can be surfaced by pathway."],["04","Re-assessment","A later check-in closes the loop and can trigger escalation."]].map(([n,t,d]) => <div className="loop-card" key={n}><span>{n}</span><h3>{t}</h3><p>{d}</p></div>)}</div></section>
    <footer className="landing-footer"><Brand compact /><span>Frontend-only prototype · Backend integration ready</span></footer>
  </main>;
}

function Feature({ icon, title, text }) { return <div className="feature-card"><div className="feature-icon">{icon}</div><div><h3>{title}</h3><p>{text}</p></div></div>; }
