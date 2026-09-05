import { api, apiConfig } from "./api";

export async function submitCheckIn(payload) {
  return api.post(apiConfig.checkIn, payload);
}

export async function getInsights(params) {
  return api.get(apiConfig.insights, { params });
}

export async function sendCounselorMessage(payload) {
  return api.post(apiConfig.counselorMessages, payload);
}
