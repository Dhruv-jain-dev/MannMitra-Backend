import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AmbientBackground from "./components/AmbientBackground";
import Layout from "./components/Layout";
import { clearUser, getCurrentProfile, getStoredUser, restoreSession } from "./services/auth";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ChangePassword from "./pages/ChangePassword";
import StudentDashboard from "./pages/StudentDashboard";
import MannMitra from "./pages/MannMitra";
import CheckIn from "./pages/CheckIn";
import WellnessZone from "./pages/WellnessZone";
import Insights from "./pages/Insights";
import CounselorDashboard from "./pages/CounselorDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import CounselorCases from "./pages/CounselorCases";
import CounselorStudents from "./pages/CounselorStudents";
import CounselorProfile from "./pages/CounselorProfile";
import CounselorMessages from "./pages/CounselorMessages";
import CounselorInterventions from "./pages/CounselorInterventions";
import CounselorFollowups from "./pages/CounselorFollowups";
import CounselorAnalytics from "./pages/CounselorAnalytics";
import AdminDepartments from "./pages/AdminDepartments";
import AdminForecast from "./pages/AdminForecast";
import AdminGovernance from "./pages/AdminGovernance";
import AdminUsers from "./pages/AdminUsers";
import AdminCases from "./pages/AdminCases";
import AdminOperations from "./pages/AdminOperations";
import AnonymousSupport from "./pages/AnonymousSupport";
import CounselorAnonymousInbox from "./pages/CounselorAnonymousInbox";

const roleHome = role => role === "student" ? "/app" : role === "counselor" ? "/app/counselor" : role === "admin" ? "/app/admin" : "/login";

function RoleRoute({ user, allowed, children }) {
  return user?.role === allowed ? children : <Navigate to={roleHome(user?.role)} replace />;
}

function AppNotFound() {
  return <main className="auth-page"><section className="auth-card"><div className="auth-head"><h1>Page not found</h1><p>The requested MannMitra page does not exist.</p></div><a className="btn btn-primary full" href="/">Return to MannMitra</a></section></main>;
}

export default function App() {
  const [user, setUser] = useState(getStoredUser);
  const [restoring, setRestoring] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const role = user?.role;
  const login = profile => setUser(profile);

  useEffect(() => {
    restoreSession()
      .then(session => session ? getCurrentProfile().then(setUser).catch(() => setUser(null)) : setUser(null))
      .catch(() => setUser(null))
      .finally(() => setRestoring(false));
  }, []);

  const logout = async () => { await clearUser(); setUser(null); setMobileOpen(false); };
  const layout = <Layout user={user} onLogout={logout} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />;

  if (restoring) return <div className="app-shell" />;
  return <div className="app-shell"><AmbientBackground /><Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<Login onLogin={login} />} />
    <Route path="/signup" element={<Signup onLogin={login} />} />
    <Route path="/change-password" element={user ? <ChangePassword onComplete={login} /> : <Navigate to="/login" replace />} />

    <Route path="/app" element={user ? (user.must_change_password ? <Navigate to="/change-password" replace /> : layout) : <Navigate to="/login" replace />}>
      <Route index element={role === "student" ? <StudentDashboard user={user} /> : <Navigate to={roleHome(role)} replace />} />
      <Route path="overview" element={<RoleRoute user={user} allowed="student"><StudentDashboard user={user} /></RoleRoute>} />
      <Route path="mannmitra" element={<RoleRoute user={user} allowed="student"><MannMitra /></RoleRoute>} />
      <Route path="checkin" element={<RoleRoute user={user} allowed="student"><CheckIn /></RoleRoute>} />
      <Route path="wellness" element={<RoleRoute user={user} allowed="student"><WellnessZone /></RoleRoute>} />
      <Route path="insights" element={<RoleRoute user={user} allowed="student"><Insights /></RoleRoute>} />
      <Route path="anonymous-support" element={<RoleRoute user={user} allowed="student"><AnonymousSupport /></RoleRoute>} />

      <Route path="admin" element={<RoleRoute user={user} allowed="admin"><AdminDashboard /></RoleRoute>} />
      <Route path="admin/users" element={<RoleRoute user={user} allowed="admin"><AdminUsers /></RoleRoute>} />
      <Route path="admin/cases" element={<RoleRoute user={user} allowed="admin"><AdminCases /></RoleRoute>} />
      <Route path="admin/operations" element={<RoleRoute user={user} allowed="admin"><AdminOperations /></RoleRoute>} />
      <Route path="admin/departments" element={<RoleRoute user={user} allowed="admin"><AdminDepartments /></RoleRoute>} />
      <Route path="admin/forecast" element={<RoleRoute user={user} allowed="admin"><AdminForecast /></RoleRoute>} />
      <Route path="admin/governance" element={<RoleRoute user={user} allowed="admin"><AdminGovernance /></RoleRoute>} />

      <Route path="counselor" element={<RoleRoute user={user} allowed="counselor"><CounselorDashboard /></RoleRoute>} />
      <Route path="counselor/students" element={<RoleRoute user={user} allowed="counselor"><CounselorStudents /></RoleRoute>} />
      <Route path="counselor/profile" element={<RoleRoute user={user} allowed="counselor"><CounselorProfile /></RoleRoute>} />
      <Route path="counselor/messages" element={<RoleRoute user={user} allowed="counselor"><CounselorMessages /></RoleRoute>} />
      <Route path="counselor/anonymous-support" element={<RoleRoute user={user} allowed="counselor"><CounselorAnonymousInbox /></RoleRoute>} />
      <Route path="counselor/cases" element={<RoleRoute user={user} allowed="counselor"><CounselorCases /></RoleRoute>} />
      <Route path="counselor/interventions" element={<RoleRoute user={user} allowed="counselor"><CounselorInterventions /></RoleRoute>} />
      <Route path="counselor/followups" element={<RoleRoute user={user} allowed="counselor"><CounselorFollowups /></RoleRoute>} />
      <Route path="counselor/analytics" element={<RoleRoute user={user} allowed="counselor"><CounselorAnalytics /></RoleRoute>} />
    </Route>

    <Route path="*" element={<AppNotFound />} />
  </Routes></div>;
}
