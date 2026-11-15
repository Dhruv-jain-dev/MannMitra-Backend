import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Filter, Search, ShieldCheck, UserRound, X } from "lucide-react";
import PageTitle from "../components/PageTitle";
import RiskBadge from "../components/RiskBadge";
import { getCounselorCase, getCounselorCases, updateCounselorCase } from "../services/counselor";

export default function CounselorPriorityCases() {
  const [cases, setCases] = useState([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [notes, setNotes] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const loadCases = async () => {
    setLoading(true); setError("");
    try { setCases((await getCounselorCases()).data); }
    catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to load assigned cases."); }
    finally { setLoading(false); }
  };
  useEffect(() => { loadCases(); }, []);

  const filtered = useMemo(() => cases.filter(item => {
    const text = `${item.student_id} ${item.summary} ${item.priority} ${item.status}`.toLowerCase();
    const matchesText = text.includes(query.toLowerCase());
    const matchesFilter = filter === "All" || (filter === "Priority" ? item.priority === "priority" : filter === "Moderate" ? item.priority === "moderate" : item.priority === "stable");
    return matchesText && matchesFilter;
  }), [cases, query, filter]);
  const priorityCount = cases.filter(item => item.priority === "priority" && item.status !== "closed").length;
  const moderateCount = cases.filter(item => item.priority === "moderate" && item.status !== "closed").length;
  const stableCount = cases.filter(item => item.priority === "stable").length;

  const selectCase = async item => {
    setSelected(item); setDetail(null); setDetailLoading(true);
    try { const response = (await getCounselorCase(item.id)).data; setDetail(response); setNotes(response.details || ""); }
    catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to load case details."); }
    finally { setDetailLoading(false); }
  };

  const changeStatus = async status => {
    if (!selected) return;
    try {
      const response = await updateCounselorCase(selected.id, { status });
      setSelected(response.data); setDetail(response.data); await loadCases();
    } catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to update the case."); }
  };

  const saveNotes = async () => {
    if (!selected) return;
    setSavingNotes(true); setError("");
    try { const response = await updateCounselorCase(selected.id, { details: notes.trim() || null }); setSelected(response.data); setDetail(response.data); setNotes(response.data.details || ""); await loadCases(); }
    catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to save counselor notes."); }
    finally { setSavingNotes(false); }
  };

  return <>
    <PageTitle eyebrow="PRIORITY CASES" title="Review assigned students who may need attention." subtitle="Use transparent support signals for human follow-up. Only your assigned cases are available here." />
    <div className="role-kpi-grid"><Kpi label="Priority review" value={priorityCount} detail="Open human review queue" tone="danger"/><Kpi label="Moderate" value={moderateCount} detail="Open support cases" tone="warning"/><Kpi label="Stable" value={stableCount} detail="Assigned cases"/><Kpi label="Total cases" value={cases.length} detail="Your assigned records"/></div>
    {error && <div className="card placeholder-panel"><p>{error}</p><button className="btn btn-soft" onClick={loadCases}>Try again</button></div>}
    <section className="card workspace-card"><div className="workspace-toolbar"><div className="search-box"><Search size={14}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search student ID or case summary..."/></div><div className="filter-row"><Filter size={13}/>{["All","Priority","Moderate","Stable"].map(x=><button key={x} className={`filter-chip ${filter===x?"active":""}`} onClick={()=>setFilter(x)}>{x}</button>)}</div></div>{loading ? <div className="empty-state"><p>Loading assigned cases…</p></div> : <><div className="case-list">{filtered.map(item=><button className="case-row" key={item.id} onClick={()=>selectCase(item)}><div className="case-avatar"><UserRound size={16}/></div><div className="case-main"><b>{item.student_id}</b><span>{item.summary}</span></div><div><RiskBadge level={priorityLabel(item.priority)}/><small>{item.status.replace("_", " ")}</small></div><div className="trend">{item.latest_check_in ? `Stress ${item.latest_check_in.stress_level}/10` : "No check-in"}</div><div className="case-note">{item.next_follow_up ? `Follow-up ${formatDate(item.next_follow_up)}` : "No follow-up scheduled"}</div><ArrowRight size={15}/></button>)}</div>{!filtered.length && <div className="empty-state"><Search size={24}/><h3>No matching cases</h3><p>{cases.length ? "Try another student ID, summary or priority filter." : "No cases have been assigned to you yet."}</p></div>}</>}</section>
    <div className="two-col-workspace"><section className="card workspace-card"><SectionTitle icon={<CheckCircle2 size={17}/>} eyebrow="REVIEW CHECKLIST" title="Before contacting a student"/><div className="check-list"><Check text="Review recent check-in context"/><Check text="Check existing follow-up status"/><Check text="Use the minimum necessary information"/><Check text="Document the human decision after review"/></div></section><section className="card workspace-card"><SectionTitle icon={<ShieldCheck size={17}/>} eyebrow="SAFETY PATHWAY" title="Escalation principles"/><div className="notice-list"><Notice icon={<AlertTriangle size={15}/>} title="High-risk signals" text="Follow institutional crisis protocol and verified emergency resources." danger/><Notice icon={<ShieldCheck size={15}/>} title="Human-led decisions" text="AI signals support review; they do not diagnose or decide interventions."/></div></section></div>
    {selected && <div className="drawer-backdrop" onClick={()=>setSelected(null)}><aside className="case-drawer" onClick={e=>e.stopPropagation()}><button className="drawer-close" onClick={()=>setSelected(null)}><X size={16}/></button>{detailLoading ? <p>Loading case details…</p> : detail && <><span className="eyebrow">CASE REVIEW</span><h2>{detail.student_id}</h2><p className="panel-subtext">{detail.summary}</p><RiskBadge level={priorityLabel(detail.priority)}/><div className="drawer-stat"><span>Status</span><b>{detail.status.replace("_", " ")}</b></div><div className="drawer-stat"><span>Latest check-in</span><b>{detail.latest_check_in ? `${detail.latest_check_in.mood} · stress ${detail.latest_check_in.stress_level}/10` : "None"}</b></div><div className="drawer-block"><b>Counselor notes</b><textarea value={notes} maxLength={4000} rows={4} onChange={event=>setNotes(event.target.value)} placeholder="Record a concise support note…"/><button className="btn btn-soft btn-small" onClick={saveNotes} disabled={savingNotes}>{savingNotes ? "Saving…" : "Save notes"}</button></div><div className="drawer-block"><b>Recent check-ins</b>{detail.check_ins?.length ? detail.check_ins.slice(0, 5).map(item=><p key={item.id}>{formatDate(item.created_at)} · {item.mood} · stress {item.stress_level}/10</p>) : <p>No check-ins available.</p>}</div><div className="drawer-actions">{detail.status !== "in_progress" && detail.status !== "closed" && <button className="btn btn-primary" onClick={()=>changeStatus("in_progress")}>Start follow-up</button>}{detail.status !== "closed" && <button className="btn btn-soft" onClick={()=>changeStatus("closed")}>Mark closed</button>}</div></>}</aside></div>}
  </>;
}

function priorityLabel(priority) { return priority === "priority" ? "Priority review" : priority === "moderate" ? "Moderate support" : "Stable signal"; }
function formatDate(value) { return new Date(value).toLocaleDateString(); }
function Kpi({label,value,detail,tone=""}){return <div className={`card role-kpi ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>}
function SectionTitle({icon,eyebrow,title}){return <div className="section-title-row"><div className="section-icon">{icon}</div><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div></div>}
function Check({text}){return <div className="check-item"><CheckCircle2 size={15}/><span>{text}</span></div>}
function Notice({icon,title,text,danger}){return <div className={`notice-item ${danger?"danger": ""}`}><div>{icon}</div><span><b>{title}</b><small>{text}</small></span></div>}
