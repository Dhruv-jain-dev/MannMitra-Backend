import axios from "axios";
import { getAccessToken } from "./auth";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: 15000,
  headers: { "Content-Type": "application/json" }
});

api.interceptors.request.use(config => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const apiConfig = {
  health: "/health",
  conversations: "/api/conversations",
  mannmitraText: "/api/mannmitra/text",
  mannmitraVoice: "/api/mannmitra/voice",
  checkIn: "/api/wellbeing/check-in",
  insights: "/api/wellbeing/insights",
  counselorMessages: "/api/counselor/messages"
};
