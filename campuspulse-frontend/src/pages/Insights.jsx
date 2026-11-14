import { Activity, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PageTitle from "../components/PageTitle";
import PrivacyNote from "../components/PrivacyNote";
import { getInsights } from "../services/wellbeing";

export default function Insights() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadInsights = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getInsights();
      setData(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || "Unable to load your insights.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInsights();
    window.addEventListener("campuspulse:checkin-saved", loadInsights);
    return () => window.removeEventListener("campuspulse:checkin-saved", loadInsights);
  }, []);

  const trends = useMemo(() => data?.recent_trends || [], [data]);
  const chartPoints = useMemo(() => trends.map((item, index) => {
    const x = trends.length === 1 ? 350 : (index / (trends.length - 1)) * 700;
    const y = 205 - (Number(item.stress_level) / 10) * 160;
    return `${x},${y}`;
  }).join(" "), [trends]);
  const commonMood = useMemo(() => Object.entries(data?.mood_distribution || {}).sort((a, b) => b[1] - a[1])[0]?.[0], [data]);
  const note = data?.average_stress == null ? "Complete a check-in to start seeing your personal patterns." : data.average_stress >= 7 ? "Your recent stress average is elevated. Consider a gentle coping step or human support." : data.average_stress >= 4 ? "Your recent check-ins show a moderate stress pattern. Small regular pauses may help." : "Your recent check-ins show a lower stress pattern. Keep noticing what supports you.";

  return <><PageTitle eyebrow="MY INSIGHTS" title="Your wellbeing patterns." subtitle="Supportive trends calculated from your own saved check-ins." />{loading ? <div className="card placeholder-panel"><p>Loading your personal insights…</p></div> : error ? <div className="card placeholder-panel"><h2>Insights unavailable</h2><p>{error}</p><button className="btn btn-soft" onClick={loadInsights}>Try again</button></div> : !data?.check_in_count ? <div className="card placeholder-panel"><div className="support-icon"><Sparkles/></div><h2>Your insights will appear here.</h2><p>Complete your first check-in to begin building a private picture of your wellbeing patterns.</p></div> : <><div className="stats-grid"><Stat label="Check-ins" value={data.check_in_count} detail="Saved entries"/><Stat label="Average stress" value={data.average_stress ?? "—"} suffix="/10" detail="Across your records"/><Stat label="Most common mood" value={commonMood || "—"} detail="From your saved moods"/></div><div className="insights-grid"><div className="card chart-card"><div className="card-top"><div><span className="eyebrow">RECENT TREND</span><h2>Stress signals</h2></div><Activity size={18}/></div><div className="fake-chart"><div className="grid-lines"/><svg viewBox="0 0 700 230" preserveAspectRatio="none"><polyline points={chartPoints} fill="none" stroke="currentColor" strokeWidth="4"/></svg><div className="chart-labels">{trends.map((item, index) => <span key={`${item.date}-${index}`}>{new Date(item.date).toLocaleDateString(undefined, { weekday: "short" })}</span>)}</div></div></div><div className="card insight-note"><div className="support-icon"><Sparkles/></div><span className="eyebrow">PERSONAL NOTE</span><h2>{commonMood ? `Your recent mood is mostly ${commonMood}.` : "Your check-ins are building a pattern."}</h2><p>{note}</p></div></div></>}<PrivacyNote>These insights are calculated from your own check-ins and are not a diagnosis. Personal records remain purpose-limited and student-scoped.</PrivacyNote></>;
}

function Stat({ label, value, suffix = "", detail }) {
  return <div className="stat-card card"><span>{label}</span><strong>{value}<small>{suffix}</small></strong><div className="progress"><i style={{ width: `${typeof value === "number" ? Math.min(100, value * 10) : 0}%` }}/></div><em>{detail}</em></div>;
}
