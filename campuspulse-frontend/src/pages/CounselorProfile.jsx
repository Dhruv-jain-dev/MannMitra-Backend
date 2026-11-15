import { LogOut, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageTitle from "../components/PageTitle";
import { clearUser } from "../services/auth";
import { getCounselorProfile } from "../services/counselor";

export default function CounselorProfile() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getCounselorProfile().then(response => setProfile(response.data)).catch(e => setError(e.response?.data?.detail || e.message || "Unable to load counselor profile.")); }, []);
  const logout = async () => { await clearUser(); navigate("/", { replace: true }); window.location.reload(); };
  return <><PageTitle eyebrow="COUNSELOR PROFILE" title="Your support workspace identity." subtitle="Account details are read from the authenticated backend profile." />{error ? <section className="card placeholder-panel"><p>{error}</p></section> : <section className="card workspace-card profile-card"><div className="profile-hero"><div className="avatar large"><UserRound size={24}/></div><div><span className="eyebrow">VERIFIED ROLE</span><h2>{profile?.role || "Loading…"}</h2><p className="panel-subtext">{profile?.department || "Department not specified"}</p></div></div><div className="detail-grid"><span>Identity</span><b>{profile?.id || "Loading…"}</b><span>Role</span><b>{profile?.role || "Loading…"}</b><span>Department</span><b>{profile?.department || "Not specified"}</b><span>Profile created</span><b>{profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : "Loading…"}</b></div><div className="privacy-note"><ShieldCheck size={16}/><span>Case and student access is enforced by the backend using your authenticated Supabase identity.</span></div><button className="btn btn-soft" onClick={logout}><LogOut size={14}/> Sign out</button></section>}</>;
}
