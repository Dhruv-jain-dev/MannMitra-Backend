import { useState } from "react";
import { games } from "../data";
import { Brain, Heart, Sparkles, Target, Wind } from "lucide-react";
import PageTitle from "../components/PageTitle";
import GameModal from "../games/GameModal";

const icons = { Wind, Target, Brain, Sparkles, Heart };
export default function WellnessZone() { const [selected, setSelected] = useState(null); return <><PageTitle eyebrow="WELLNESS ZONE" title="Small activities. No pressure." subtitle="Choose a short reset that matches what you need right now." /><div className="games-grid">{games.map(g => { const Icon = icons[g.icon] || Sparkles; return <button className="game-card card" key={g.id} onClick={() => setSelected(g)}><div className="game-card-top"><div className="game-icon"><Icon size={20}/></div><span>{g.duration}</span></div><span className="game-tag">{g.tag}</span><h3>{g.title}</h3><p>{g.description}</p><span className="game-open">Start activity →</span></button>; })}</div>{selected && <GameModal game={selected} onClose={() => setSelected(null)} />}</>; }
