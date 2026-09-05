import { ArrowRight, HeartHandshake, Mail, Phone, Users } from "lucide-react";
import { counselors } from "../data";

export default function CounselorConnect() {
  return <section className="support-hub">
    <div className="support-hub-heading"><div><span className="eyebrow">SUPPORT HUB</span><h2>Support that feels easy to reach.</h2><p>Connect with a counselor for planned support, or use immediate helplines when you need urgent help.</p></div><HeartHandshake size={27} /></div>
    <div className="support-hub-grid">
      <div className="support-panel card">
        <div className="panel-heading"><div><span className="section-label">CONNECT WITH A COUNSELOR</span><h3>Choose someone to contact.</h3></div><Users size={18} /></div>
        <div className="counselor-list">
          {counselors.map(c => <article className="counselor-card" key={c.id}>
            <div className="counselor-avatar">{c.name.split(" ").map(x => x[0]).slice(0, 2).join("")}</div>
            <div className="counselor-info"><h3>{c.name}</h3><p>{c.role} · {c.specialty}</p><div className="counselor-meta"><span className="availability">{c.availability}</span><span><Mail size={11} /> {c.email}</span><span><Phone size={11} /> {c.phone}</span></div></div>
            <div className="counselor-actions"><a className="btn btn-soft" href={`mailto:${c.email}?subject=CampusPulse%20support`}>Email <ArrowRight size={14} /></a><a className="btn btn-ghost" href={`tel:${c.phone.replace(/\D/g, "")}`}>Call <Phone size={14} /></a></div>
          </article>)}
        </div>
        <p className="tiny-note">Demo contact details are placeholders. Replace them with your institution's verified counselor contacts before deployment.</p>
      </div>

      <div className="support-panel immediate-panel card">
        <div className="panel-heading"><div><span className="section-label">NEED IMMEDIATE SUPPORT?</span><h3>Help is available now.</h3></div><HeartHandshake size={18} /></div>
        <div className="emergency-stack">
          <a className="emergency-card" href="tel:14416"><div className="emergency-icon"><HeartHandshake size={20} /></div><div><b>Tele-MANAS</b><p>24×7 mental-health counselling support.</p><strong>Call 14416</strong></div><Phone size={17} /></a>
          <a className="emergency-card emergency-red" href="tel:112"><div className="emergency-icon"><Phone size={20} /></div><div><b>Emergency · 112</b><p>Urgent police, fire, medical or other emergency assistance.</p><strong>Call 112</strong></div><Phone size={17} /></a>
        </div>
        <div className="support-note"><HeartHandshake size={15} /><span>For urgent physical danger, use 112. For mental-health counselling support, use Tele-MANAS.</span></div>
      </div>
    </div>
  </section>;
}
