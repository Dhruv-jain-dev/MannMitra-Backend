export default function RiskBadge({ level = "Stable Signal" }) {
  const tone = level.toLowerCase().includes("priority") ? "priority" : level.toLowerCase().includes("moderate") ? "moderate" : "stable";
  return <span className={`priority-pill ${tone}`}>{level}</span>;
}
