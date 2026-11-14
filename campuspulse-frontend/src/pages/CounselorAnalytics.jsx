import { BarChart3, ShieldCheck } from "lucide-react";
import PageTitle from "../components/PageTitle";

export default function CounselorAnalytics() {
  return <><PageTitle eyebrow="CAMPUS ANALYTICS" title="Institutional analytics for counselor capacity." subtitle="Aggregate campus analytics require a separately authorized admin view and are not exposed in the counselor portal."/><section className="card workspace-card"><div className="section-title-row"><div className="section-icon"><BarChart3 size={17}/></div><div><span className="eyebrow">ANALYTICS UNAVAILABLE</span><h2>No counselor aggregate dataset</h2></div></div><p className="panel-subtext">This portal shows only assigned cases and support workflows. No department, student-population, forecast, or campus-wide metrics are fabricated here.</p></section><div className="analytics-callout"><ShieldCheck size={17}/><div><b>Privacy guardrail</b><p>Campus-wide aggregates are restricted to the admin portal. Individual student records and MannMitra conversations remain excluded.</p></div></div></>;
}
