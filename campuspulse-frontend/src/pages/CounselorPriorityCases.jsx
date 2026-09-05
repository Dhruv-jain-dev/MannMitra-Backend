import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Filter, Search, ShieldCheck, UserRound, X } from "lucide-react";
import PageTitle from "../components/PageTitle";
import RiskBadge from "../components/RiskBadge";
import { priorityStudents } from "../data";

export default function CounselorPriorityCases() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState(null);
  const filtered = useMemo(() => priorityStudents.filter(s => {
    const matchesText = `${s.id} ${s.department} ${s.year}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All" || (filter === "Priority" ? s.priority.includes("Priority") : filter === "Moderate" ? s.priority.includes("Moderate") : s.priority.includes("Stable"));
    return matchesText && matchesFilter;
  }), [query, filter]);
  return <>
    <PageTitle eyebrow="PRIORITY CASES" title="Review students who may need attention." subtitle="Prioritize human follow-up using transparent support signals. This frontend uses demo records until your backend is connected." />
    <div className="role-kpi-grid"><Kpi label="Priority review" value="3" detail="Human review queue" tone="danger"/><Kpi label="Moderate" value="8" detail="Support pathways" tone="warning"/><Kpi label="Stable" value="409" detail="Routine monitoring"/><Kpi label="Reviewed today" value="12" detail="Counselor actions"/></div>
    <section className="card workspace-card">
      <div className="workspace-toolbar"><div className="search-box"><Search size={14}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search student ID, department..."/></div><div className="filter-row"><Filter size={13}/>{["All","Priority","Moderate","Stable"].map(x=><button key={x} className={`filter-chip ${filter===x?"active":""}`} onClick={()=>setFilter(x)}>{x}</button>)}</div></div>
      <div className="case-list">{filtered.map(s=><button className="case-row" key={s.id} onClick={()=>setSelected(s)}><div className="case-avatar"><UserRound size={16}/></div><div className="case-main"><b>{s.id}</b><span>{s.department} · {s.year}</span></div><div><RiskBadge level={s.priority}/><small>Signal {s.score}</small></div><div className={`trend ${s.trend === "Improving" ? "improving" : "declining"}`}>{s.trend}</div><div className="case-note">{s.note}</div><ArrowRight size={15}/></button>)}</div>
      {!filtered.length && <div className="empty-state"><Search size={24}/><h3>No matching cases</h3><p>Try another student ID, department or priority filter.</p></div>}
    </section>
    <div className="two-col-workspace"><section className="card workspace-card"><SectionTitle icon={<CheckCircle2 size={17}/>} eyebrow="REVIEW CHECKLIST" title="Before contacting a student"/><div className="check-list"><Check text="Review recent check-in context"/><Check text="Check existing follow-up status"/><Check text="Use the minimum necessary information"/><Check text="Document the human decision after review"/></div></section><section className="card workspace-card"><SectionTitle icon={<ShieldCheck size={17}/>} eyebrow="SAFETY PATHWAY" title="Escalation principles"/><div className="notice-list"><Notice icon={<AlertTriangle size={15}/>} title="High-risk signals" text="Follow institutional crisis protocol and verified emergency resources." danger/><Notice icon={<ShieldCheck size={15}/>} title="Human-led decisions" text="AI signals support review; they do not diagnose or decide interventions."/></div></section></div>
    {selected && <div className="drawer-backdrop" onClick={()=>setSelected(null)}><aside className="case-drawer" onClick={e=>e.stopPropagation()}><button className="drawer-close" onClick={()=>setSelected(null)}><X size={16}/></button><span className="eyebrow">CASE REVIEW</span><h2>{selected.id}</h2><p className="panel-subtext">{selected.department} · {selected.year}</p><RiskBadge level={selected.priority}/><div className="drawer-stat"><span>Signal score</span><b>{selected.score}</b></div><div className="drawer-stat"><span>Trend</span><b>{selected.trend}</b></div><div className="drawer-block"><b>Context</b><p>{selected.note}. Review recent check-ins and existing support history before choosing an action.</p></div><div className="drawer-actions"><button className="btn btn-primary">Start follow-up</button><button className="btn btn-soft">Mark reviewed</button></div></aside></div>}
  </>;
}
function Kpi({label,value,detail,tone=""}){return <div className={`card role-kpi ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>}
function SectionTitle({icon,eyebrow,title}){return <div className="section-title-row"><div className="section-icon">{icon}</div><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div></div>}
function Check({text}){return <div className="check-item"><CheckCircle2 size={15}/><span>{text}</span></div>}
function Notice({icon,title,text,danger}){return <div className={`notice-item ${danger?"danger": ""}`}><div>{icon}</div><span><b>{title}</b><small>{text}</small></span></div>}
