import { api, apiConfig } from "./api";

export async function submitCheckIn(payload) {
  return api.post(apiConfig.checkIn, payload);
}

export async function getCheckIns(params) {
  return api.get(apiConfig.checkIns, { params });
}

export async function getInsights(params) {
  return api.get(apiConfig.insights, { params });
}
