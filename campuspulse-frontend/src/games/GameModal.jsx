import { X, Wind, Target, Brain, Sparkles, Heart } from "lucide-react";
import Breathing from "./Breathing";
import FocusSprint from "./FocusSprint";
import MindMatch from "./MindMatch";
import ColorCalm from "./ColorCalm";
import MoodGarden from "./MoodGarden";
import MiniMeditation from "./MiniMeditation";

const icons={breath:Wind,focus:Target,memory:Brain,calmcolors:Sparkles,moodgarden:Heart,meditation:Wind};
const games={breath:Breathing,focus:FocusSprint,memory:MindMatch,calmcolors:ColorCalm,moodgarden:MoodGarden,meditation:MiniMeditation};
export default function GameModal({game,onClose}){const Game=games[game.id];const Icon=icons[game.id]||Sparkles;return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="game-modal"><button className="modal-close icon-btn" onClick={onClose}><X size={17}/></button><div className="game-frame-head"><div className="game-icon"><Icon size={21}/></div><div><span className="eyebrow">WELLNESS ACTIVITY · {game.duration}</span><h2>{game.title}</h2><p>{game.description}</p></div></div><Game /></div></div>}
