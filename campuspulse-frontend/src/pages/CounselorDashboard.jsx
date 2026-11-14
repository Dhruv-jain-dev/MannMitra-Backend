import { Activity, ArrowUpRight, CalendarClock, MessageCircle, ShieldCheck, Users, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PageTitle from "../components/PageTitle";
import StatCard from "../components/StatCard";
import RiskBadge from "../components/RiskBadge";
import PrivacyNote from "../components/PrivacyNote";
import { getCounselorDashboard, getCounselorMessages } from "../services/counselor";

export default function CounselorDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [messageThreads, setMessageThreads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = async () => {
    setLoading(true); setError("");
    try {
      const [dashboardResponse, messagesResponse] = await Promise.all([getCounselorDashboard(), getCounselorMessages()]);
      setDashboard(dashboardResponse.data);
      setMessageThreads(messagesResponse.data.items || []);
    }
    catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to load the counselor dashboard."); }
    finally { setLoading(false); }
  };
  useEffect(() => { loadDashboard(); }, []);

  const cases = useMemo(() => dashboard?.assigned_cases || [], [dashboard]);
  const openCases = useMemo(() => cases.filter(item => item.status !== "closed"), [cases]);
  const uniqueStudents = new Set(cases.map(item => item.student_id)).size;
  const moderateCases = cases.filter(item => item.priority === "moderate").length;
  const priorityCases = cases.filter(item => item.priority === "priority").length;

  return <>
    <PageTitle eyebrow="COUNSELOR CENTER" title="Student support command center." subtitle="Review assigned cases, follow-ups and support signals while keeping intervention decisions human-led." action={<div className="mini-user"><div className="avatar">C</div><span>Counselor workspace</span></div>} />
    <div className="signal-banner"><ShieldCheck size={20}/><div><b>CampusPulse Signal Intelligence <span className="privacy-tag">PRIVACY PROTECTED</span></b><span>Only cases assigned to your counselor account are shown. MannMitra conversations are not exposed here.</span></div></div>
    {loading ? <StateCard text="Loading assigned cases…"/> : error ? <StateCard text={error} action={<button className="btn btn-soft" onClick={loadDashboard}>Try again</button>}/> : <>
      <div className="stats-grid counselor-stats-wide"><StatCard label="Students monitored" value={uniqueStudents} detail="Unique assigned students" icon={Users}/><StatCard label="Moderate support" value={moderateCases} detail="Assigned active cases" icon={Activity}/><StatCard label="Priority review" value={priorityCases} detail="Human review queue" icon={Zap}/><StatCard label="Follow-ups due" value={dashboard.upcoming_followups.length} detail="Upcoming assigned follow-ups" icon={CalendarClock}/></div>
      <div className="counselor-dashboard-grid">
        <section className="card counselor-panel"><div className="card-top"><div><span className="eyebrow">STUDENT PRIORITY QUEUE</span><h2>Support signals needing attention</h2><p className="panel-subtext">Review only the students assigned to your counselor account.</p></div><span className="queue-count">{openCases.length} open cases</span></div><div className="priority-table"><div className="priority-head"><span>STUDENT</span><span>SUPPORT PRIORITY</span><span>STATUS</span><span>CASE SUMMARY</span></div>{openCases.length ? openCases.map(item => <div className="priority-row" key={item.id}><div><b>{item.student_id}</b><span>{item.latest_check_in ? `Latest stress ${item.latest_check_in.stress_level}/10` : "No check-in yet"}</span></div><div><RiskBadge level={priorityLabel(item.priority)}/><small>{item.latest_check_in ? `Mood: ${item.latest_check_in.mood}` : "No signal"}</small></div><div className={`trend ${item.status === "in_progress" ? "declining" : "improving"}`}>{item.status.replace("_", " ")}</div><div className="action-cell"><span>{item.summary}</span><ArrowUpRight size={14}/></div></div>) : <EmptyRow text="No open assigned cases."/>}</div></section>
        <aside className="counselor-side-stack"><section className="card mini-panel"><div className="mini-panel-head"><div><span className="eyebrow">UPCOMING</span><h3>Follow-up plan</h3></div><CalendarClock size={18}/></div>{dashboard.upcoming_followups.length ? <div className="task-list">{dashboard.upcoming_followups.map(item => <div key={item.id}><span className="task-dot urgent"/><div><b>{item.student_id}</b><small>{item.summary}</small></div></div>)}</div> : <p className="small-muted">No upcoming follow-ups.</p>}</section><section className="card mini-panel"><div className="mini-panel-head"><div><span className="eyebrow">CASE ACTIVITY</span><h3>Assigned workload</h3></div><MessageCircle size={18}/></div><div className="activity-bars"><Bar label="Open cases" value={cases.length ? Math.round((openCases.length / cases.length) * 100) : 0}/><Bar label="Priority cases" value={cases.length ? Math.round((priorityCases / cases.length) * 100) : 0}/><Bar label="Cases with follow-up" value={cases.length ? Math.round((dashboard.upcoming_followups.length / cases.length) * 100) : 0}/></div></section></aside>
      </div>
      <section className="card counselor-panel messages-panel"><div className="card-top"><div><span className="eyebrow">STUDENT MESSAGES</span><h2>Requests from students</h2></div><MessageCircle size={20}/></div>{messageThreads.length ? <div className="task-list">{messageThreads.slice(0, 5).map(thread => <div key={thread.id}><span className="task-dot urgent"/><div><b>{thread.student_id}</b><small>{thread.unread_count ? `${thread.unread_count} unread message${thread.unread_count === 1 ? "" : "s"}` : "No unread messages"}</small></div><small>{thread.messages?.at(-1)?.created_at ? new Date(thread.messages.at(-1).created_at).toLocaleString() : ""}</small></div>)}</div> : <div className="empty-state"><MessageCircle size={24}/><h3>No counselor messages yet</h3><p>Messages from assigned students will appear here.</p></div>}</section>
    </>}
    <PrivacyNote>AI signals support review; they do not diagnose or decide interventions. Case access is limited to assigned counselor records.</PrivacyNote>
  </>;
}

function priorityLabel(priority) { return priority === "priority" ? "Priority review" : priority === "moderate" ? "Moderate support" : "Stable signal"; }
function Bar({ label, value }) { return <div><span>{label}</span><b>{value}%</b><i><em style={{ width: `${value}%` }}/></i></div>; }
function EmptyRow({ text }) { return <div className="empty-state"><p>{text}</p></div>; }
function StateCard({ text, action }) { return <div className="card placeholder-panel"><p>{text}</p>{action}</div>; }
