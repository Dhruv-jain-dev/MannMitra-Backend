import { Search, ShieldCheck, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PageTitle from "../components/PageTitle";
import RiskBadge from "../components/RiskBadge";
import { getCounselorStudent, getCounselorStudents } from "../services/counselor";

export default function CounselorStudents() {
  const [students, setStudents] = useState([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try { setStudents((await getCounselorStudents()).data || []); }
    catch (e) { setError(e.response?.data?.detail || e.message || "Unable to load assigned students."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => students.filter(student => `${student.id} ${student.department || ""}`.toLowerCase().includes(query.toLowerCase())), [students, query]);
  const openStudent = async student => {
    setSelected({ ...student, loading: true }); setDetailLoading(true); setError("");
    try { setSelected((await getCounselorStudent(student.id)).data); }
    catch (e) { setError(e.response?.data?.detail || e.message || "Unable to load the student record."); setSelected(null); }
    finally { setDetailLoading(false); }
  };

  return <>
    <PageTitle eyebrow="ASSIGNED STUDENTS" title="Know the students in your care." subtitle="Only students with an active or historical case assigned to your counselor account appear here." action={<button className="btn btn-soft" onClick={load}>Refresh</button>} />
    {error && <div className="card placeholder-panel"><p>{error}</p><button className="btn btn-soft" onClick={load}>Try again</button></div>}
    <section className="card workspace-card">
      <div className="workspace-toolbar"><div className="search-box"><Search size={14}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search assigned student or department" /></div><span className="privacy-tag"><ShieldCheck size={12}/> Assignment scoped</span></div>
      {loading ? <div className="empty-state"><p>Loading assigned students…</p></div> : filtered.length ? <div className="case-list">{filtered.map(student => <button className="case-row" key={student.id} onClick={() => openStudent(student)}><div className="case-avatar"><UserRound size={16}/></div><div className="case-main"><b>{student.id}</b><span>{student.department || "Department not specified"}</span></div><div><RiskBadge level={student.latest_check_in ? riskLabel(student.latest_check_in.stress_level) : "No signal"}/><small>{student.latest_check_in ? `Stress ${student.latest_check_in.stress_level}/10` : "No check-in"}</small></div><div className="trend">{student.open_case_count} open case{student.open_case_count === 1 ? "" : "s"}</div></button>)}</div> : <div className="empty-state"><UserRound size={24}/><h3>No assigned students</h3><p>{students.length ? "No students match your search." : "Students assigned to your cases will appear here."}</p></div>}
    </section>
    {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="case-drawer" onClick={event => event.stopPropagation()}><button className="drawer-close" onClick={() => setSelected(null)}><X size={16}/></button>{detailLoading ? <p>Loading authorized student history…</p> : <><span className="eyebrow">AUTHORIZED STUDENT VIEW</span><h2>{selected.id}</h2><p className="panel-subtext">{selected.department || "Department not specified"}</p><div className="drawer-stat"><span>Open cases</span><b>{selected.open_case_count}</b></div><div className="drawer-block"><b>Recent wellbeing check-ins</b>{selected.check_ins?.length ? selected.check_ins.slice(0, 10).map(item => <p key={item.id}>{formatDate(item.created_at)} · {item.mood} · stress {item.stress_level}/10</p>) : <p>No check-ins available.</p>}</div><div className="drawer-block"><b>Assigned cases</b>{selected.cases?.length ? selected.cases.map(item => <p key={item.id}>{item.summary} · {item.status.replace("_", " ")}</p>) : <p>No assigned cases.</p>}</div></>}</aside></div>}
  </>;
}

function riskLabel(stress) { return stress >= 7 ? "Priority review" : stress >= 4 ? "Moderate support" : "Stable signal"; }
function formatDate(value) { return new Date(value).toLocaleDateString(); }
