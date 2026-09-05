const KEY = "campuspulse_user";
const ACCESS_TOKEN_KEY = "campuspulse_access_token";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}

export function saveUser(user) {
  localStorage.setItem(KEY, JSON.stringify(user));
}

export function clearUser() {
  localStorage.removeItem(KEY);
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

// Production authentication can store a JWT either on the user profile or
// under this dedicated key. The current login screen remains demo-only.
export function getAccessToken() {
  const user = getStoredUser();
  return user?.accessToken || localStorage.getItem(ACCESS_TOKEN_KEY) || null;
}

export async function authenticateDevelopmentUser(profile) {
  const response = await fetch(`${API_BASE_URL}/api/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: profile.email || profile.name })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Unable to start a backend session.");
  const authenticatedProfile = { ...profile, accessToken: data.access_token };
  localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
  saveUser(authenticatedProfile);
  return authenticatedProfile;
}

export function buildDemoProfile(role, email = "") {
  if (role === "student") return { name: "Student", email, department: "Computer Science", year: "3rd Year", role };
  if (role === "counselor") return { name: "Counselor", email, role };
  return { name: "Campus Admin", email, role: "admin" };
}
