import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AmbientBackground from "./components/AmbientBackground";
import Layout from "./components/Layout";
import { clearUser, getStoredUser } from "./services/auth";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import StudentDashboard from "./pages/StudentDashboard";
import MannMitra from "./pages/MannMitra";
import CheckIn from "./pages/CheckIn";
import WellnessZone from "./pages/WellnessZone";
import Insights from "./pages/Insights";
import CounselorDashboard from "./pages/CounselorDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import CounselorPriorityCases from "./pages/CounselorPriorityCases";
import CounselorInterventions from "./pages/CounselorInterventions";
import CounselorFollowups from "./pages/CounselorFollowups";
import CounselorAnalytics from "./pages/CounselorAnalytics";
import AdminDepartments from "./pages/AdminDepartments";
import AdminForecast from "./pages/AdminForecast";
import AdminGovernance from "./pages/AdminGovernance";

export default function App() {
  const [user, setUser] = useState(getStoredUser);
  const [mobileOpen, setMobileOpen] = useState(false);
  const role = user?.role;
  const login = profile => setUser(profile);
  const logout = () => { clearUser(); setUser(null); setMobileOpen(false); };
  return <div className="app-shell"><AmbientBackground /><Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<Login onLogin={login} />} />
    <Route path="/signup" element={<Signup onLogin={login} />} />
    <Route path="/app" element={user ? <Layout user={user} onLogout={logout} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} /> : <Navigate to="/login" replace />}>
      <Route index element={<Navigate to="overview" replace />} />
      <Route path="overview" element={role === "student" ? <StudentDashboard user={user} /> : role === "counselor" ? <CounselorDashboard /> : <AdminDashboard />} />
      {role === "student" && <>
        <Route path="mannmitra" element={<MannMitra />} /><Route path="checkin" element={<CheckIn />} /><Route path="wellness" element={<WellnessZone />} /><Route path="insights" element={<Insights />} />
      </>}
      {role === "counselor" && <>
        <Route path="counselor" element={<CounselorDashboard />} />
        <Route path="counselor/messages" element={<CounselorPriorityCases />} />
        <Route path="counselor/interventions" element={<CounselorInterventions />} />
        <Route path="counselor/followups" element={<CounselorFollowups />} />
        <Route path="counselor/analytics" element={<CounselorAnalytics />} />
      </>}
      {role === "admin" && <>
        <Route path="admin" element={<AdminDashboard />} />
        <Route path="admin/departments" element={<AdminDepartments />} />
        <Route path="admin/forecast" element={<AdminForecast />} />
        <Route path="admin/governance" element={<AdminGovernance />} />
      </>}
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></div>;
}
