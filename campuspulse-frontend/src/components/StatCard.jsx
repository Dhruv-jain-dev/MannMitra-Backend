export default function StatCard({ label, value, detail, progress, icon: Icon }) {
  return <div className="stat-card card"><div className="stat-head"><span>{label}</span>{Icon && <div className="stat-icon"><Icon size={17} /></div>}</div><strong>{value}</strong>{typeof progress === "number" && <div className="progress"><i style={{ width: `${progress}%` }} /></div>}<em>{detail}</em></div>;
}
