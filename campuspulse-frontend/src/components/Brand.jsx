import { Sparkles } from "lucide-react";

export default function Brand({ compact = false }) {
  return (
    <div className="brand">
      <div className="brand-mark"><Sparkles size={compact ? 16 : 20} /></div>
      <div>
        <div className="brand-name">Campus<span>Pulse</span></div>
        {!compact && <div className="brand-sub">Privacy-first student wellbeing</div>}
      </div>
    </div>
  );
}
