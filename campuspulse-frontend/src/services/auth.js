import { createClient } from "@supabase/supabase-js";

const KEY = "campuspulse_user";
const ACCESS_TOKEN_KEY = "campuspulse_access_token";
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const supabase = SUPABASE_URL && SUPABASE_ANON_KEY
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

let currentAccessToken = null;
if (supabase) {
  supabase.auth.onAuthStateChange((_event, session) => {
    currentAccessToken = session?.access_token || null;
    if (currentAccessToken) localStorage.setItem(ACCESS_TOKEN_KEY, currentAccessToken);
    else localStorage.removeItem(ACCESS_TOKEN_KEY);
  });
}

function requireSupabase() {
  if (!supabase) throw new Error("Supabase authentication is not configured for this frontend.");
  return supabase;
}

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}

export function saveUser(user) { localStorage.setItem(KEY, JSON.stringify(user)); }

export async function clearUser() {
  if (supabase) await supabase.auth.signOut();
  currentAccessToken = null;
  localStorage.removeItem(KEY);
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getAccessToken() {
  return currentAccessToken || localStorage.getItem(ACCESS_TOKEN_KEY) || null;
}

export async function restoreSession() {
  const client = requireSupabase();
  const { data, error } = await client.auth.getSession();
  if (error) throw error;
  currentAccessToken = data.session?.access_token || null;
  return data.session;
}

export async function authenticateUser(email, password) {
  const client = requireSupabase();
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw error;
  currentAccessToken = data.session?.access_token || null;
  localStorage.setItem(ACCESS_TOKEN_KEY, currentAccessToken || "");
  const profile = { id: data.user.id, email: data.user.email, accessToken: currentAccessToken };
  saveUser(profile);
  return profile;
}

export async function getCurrentProfile() {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
  if (!response.ok) throw new Error("The authenticated profile could not be loaded.");
  const profile = await response.json();
  const stored = { ...getStoredUser(), id: profile.id, role: profile.role, accessToken: getAccessToken() };
  saveUser(stored);
  return stored;
}

export async function synchronizeStudentProfile() {
  const response = await fetch(`${API_BASE_URL}/api/auth/profile`, { method: "POST", headers: { Authorization: `Bearer ${getAccessToken()}` } });
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || "The student profile could not be created."); }
  return response.json();
}

export async function registerUser(email, password) {
  const client = requireSupabase();
  const { data, error } = await client.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

export async function requestPasswordReset(email) {
  const client = requireSupabase();
  const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/login` });
  if (error) throw error;
}

export async function verifyRoleAccess(role) {
  const endpoint = role === "admin" ? "/api/admin/dashboard" : role === "counselor" ? "/api/counselor/dashboard" : "/api/wellbeing/insights";
  const response = await fetch(`${API_BASE_URL}${endpoint}`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `The signed-in account does not have ${role} access.`);
  }
}

// Kept only as a compatibility helper for isolated legacy UI tests. It does
// not issue a token or authenticate against the backend.
export function buildDemoProfile(role, email = "") { return { name: role === "admin" ? "Campus Admin" : role, email, role }; }
