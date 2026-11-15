import { Search, UserPlus, Users, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageTitle from "../components/PageTitle";
import { getAdminUser, getAdminUsers, provisionAdminUser, updateAdminUserRole } from "../services/counselor";

const roles = ["all", "student", "counselor", "admin"];
const emptyForm = { email: "", id: "", role: "counselor", department: "", method: "invite", password: "", password_confirmation: "" };

export default function AdminUsers() {
  const [users, setUsers] = useState([]); const [page, setPage] = useState(1); const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("all"); const [query, setQuery] = useState(""); const [selected, setSelected] = useState(null);
  const [showProvision, setShowProvision] = useState(false); const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [form, setForm] = useState(emptyForm);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const response = await getAdminUsers({ page, page_size: 25, ...(filter !== "all" ? { role: filter } : {}) }); setUsers(response.data.items || []); setTotal(response.data.total || 0); }
    catch (e) { setError(e.response?.data?.detail || "Unable to load users."); }
    finally { setLoading(false); }
  }, [filter, page]);
  useEffect(() => { setPage(1); }, [filter]);
  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => users.filter(user => `${user.id} ${user.department || ""}`.toLowerCase().includes(query.toLowerCase())), [users, query]);
  const inspect = async id => { try { setSelected((await getAdminUser(id)).data); } catch (e) { setError(e.response?.data?.detail || "Unable to load user details."); } };
  const changeRole = async (user, role) => {
    setSaving(true); setError(""); setNotice("");
    try { const response = await updateAdminUserRole(user.id, { role }); setUsers(current => current.map(item => item.id === user.id ? response.data : item)); setSelected(response.data); setNotice("Role updated through the authorized backend."); }
    catch (e) { setError(e.response?.data?.detail || "Role update was rejected."); }
    finally { setSaving(false); }
  };
  const provision = async event => {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = { email: form.email, ...(form.id ? { id: form.id } : {}), role: form.role, ...(form.department ? { department: form.department } : {}), method: form.method };
      if (form.method === "temporary_password") { payload.password = form.password; payload.password_confirmation = form.password_confirmation; }
      await provisionAdminUser(payload);
      setShowProvision(false); setForm(emptyForm); setNotice(form.method === "temporary_password" ? "Temporary-password identity created. The user must change it at first login." : "Invitation sent through Supabase Auth.");
      await load();
    } catch (e) { setError(e.response?.data?.detail || "Provisioning was rejected."); }
    finally { setSaving(false); }
  };

  return <>
    <PageTitle eyebrow="PEOPLE & ACCESS" title="Manage the people behind support." subtitle="Profiles, roles and provisioning are controlled by the authenticated backend." action={<button type="button" className="btn btn-primary" aria-label="Create user or provision identity" onClick={() => { setError(""); setNotice(""); setShowProvision(true); }}><UserPlus size={14}/> Create User</button>} />
    {notice && <div className="admin-notice success">{notice}</div>}{error && <div className="admin-notice error">{error}</div>}
    <section className="card workspace-card"><div className="admin-toolbar"><div className="search-box"><Search size={15}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by identity or department" /></div><div className="filter-tabs">{roles.map(role => <button key={role} className={filter === role ? "active" : ""} onClick={() => setFilter(role)}>{role}</button>)}</div></div>
      {loading ? <AdminState text="Loading user profiles…"/> : visible.length ? <><div className="admin-table"><div className="admin-table-head"><span>IDENTITY</span><span>ROLE</span><span>DEPARTMENT</span><span>CREATED</span><span></span></div>{visible.map(user => <button className="admin-table-row" key={user.id} onClick={() => inspect(user.id)}><span className="identity-cell"><span className="avatar small">{user.role.slice(0, 1).toUpperCase()}</span><b>{user.id}</b></span><span><span className={`role-pill ${user.role}`}>{user.role}</span></span><span>{user.department || "Unassigned"}</span><span>{formatDate(user.created_at)}</span><span>View →</span></button>)}</div><div className="admin-pagination"><span>Showing {((page - 1) * 25) + 1}–{Math.min(page * 25, total)} of {total}</span><div><button className="btn btn-soft btn-small" disabled={page === 1} onClick={() => setPage(current => current - 1)}>Previous</button><button className="btn btn-soft btn-small" disabled={page * 25 >= total} onClick={() => setPage(current => current + 1)}>Next</button></div></div></> : <AdminState text="No matching profiles found."/>}
    </section>
    {selected && <div className="admin-drawer-backdrop" onClick={() => setSelected(null)}><aside className="admin-drawer" onClick={event => event.stopPropagation()}><button className="drawer-close" onClick={() => setSelected(null)}><X size={16}/></button><span className="eyebrow">PROFILE DETAIL</span><h2>{selected.id}</h2><p className="panel-subtext">Application profile backed by PostgreSQL. Authentication credentials are never displayed here.</p><div className="detail-grid"><span>Role</span><b>{selected.role}</b><span>Department</span><b>{selected.department || "Unassigned"}</b><span>Created</span><b>{formatDate(selected.created_at)}</b></div><label className="admin-field">Change permitted role<select value={selected.role} disabled={saving} onChange={event => changeRole(selected, event.target.value)}><option value="student">student</option><option value="counselor">counselor</option><option value="admin">admin</option></select></label></aside></div>}
    {showProvision && <div className="admin-drawer-backdrop" onClick={() => setShowProvision(false)}><form className="admin-modal" onSubmit={provision} onClick={event => event.stopPropagation()}><button type="button" className="drawer-close" onClick={() => setShowProvision(false)}><X size={16}/></button><span className="eyebrow">AUTHORIZED PROVISIONING</span><h2>Create User</h2><p className="panel-subtext">The backend performs the Auth operation. Passwords are sent only for temporary creation and are never returned or stored by this application.</p><label className="admin-field">Account creation method<select value={form.method} onChange={event => setForm({ ...form, method: event.target.value, password: "", password_confirmation: "" })}><option value="invite">Send invitation email</option><option value="temporary_password">Set temporary password</option></select></label><label className="admin-field">Email<input required type="email" value={form.email} onChange={event => setForm({ ...form, email: event.target.value })}/></label>{form.method === "invite" && <label className="admin-field">Existing Auth UUID (optional)<input value={form.id} onChange={event => setForm({ ...form, id: event.target.value })}/></label>}{form.method === "temporary_password" && <><label className="admin-field">Temporary password<input required type="password" autoComplete="new-password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })}/></label><label className="admin-field">Confirm temporary password<input required type="password" autoComplete="new-password" value={form.password_confirmation} onChange={event => setForm({ ...form, password_confirmation: event.target.value })}/></label><p className="small-muted">At least 12 characters with uppercase, lowercase, number and symbol. The user must change it at first login.</p></>}<label className="admin-field">Role<select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })}><option value="student">student</option><option value="counselor">counselor</option><option value="admin">admin</option></select></label><label className="admin-field">Department<input value={form.department} onChange={event => setForm({ ...form, department: event.target.value })}/></label><button className="btn btn-primary full" disabled={saving}>{saving ? "Creating…" : "Create User"}</button></form></div>}
  </>;
}

function formatDate(value) { return value ? new Date(value).toLocaleDateString() : "—"; }
function AdminState({ text }) { return <div className="empty-state"><Users size={20}/><p>{text}</p></div>; }
