import { api, apiConfig } from "./api";

export function getCounselorDashboard() {
  return api.get(apiConfig.counselorDashboard);
}

export function getCounselorCases() {
  return api.get(apiConfig.counselorCases);
}

export function getCounselorCase(caseId) {
  return api.get(`${apiConfig.counselorCases}/${caseId}`);
}

export function updateCounselorCase(caseId, payload) {
  return api.patch(`${apiConfig.counselorCases}/${caseId}`, payload);
}

export function getCounselorInterventions() { return api.get(apiConfig.counselorInterventions); }
export function createCounselorIntervention(payload) { return api.post(apiConfig.counselorInterventions, payload); }
export function updateCounselorIntervention(id, payload) { return api.patch(`${apiConfig.counselorInterventions}/${id}`, payload); }
export function getCounselorFollowups() { return api.get(apiConfig.counselorFollowups); }
export function createCounselorFollowup(payload) { return api.post(apiConfig.counselorFollowups, payload); }
export function updateCounselorFollowup(id, payload) { return api.patch(`${apiConfig.counselorFollowups}/${id}`, payload); }

export function getAdminDashboard() { return api.get(apiConfig.adminDashboard); }
export function getAdminDepartments(params = {}) { return api.get(apiConfig.adminDepartments, { params }); }
export function getAdminAnalytics(params = {}) { return api.get(apiConfig.adminAnalytics, { params }); }

export function getCounselorContacts() {
  return api.get(apiConfig.counselorContacts);
}

export function getCounselorMessages() {
  return api.get(apiConfig.counselorMessages);
}

export function sendCounselorMessage(payload) {
  return api.post(apiConfig.counselorMessages, payload);
}

export function markCounselorMessagesRead(conversationId) {
  return api.post(`${apiConfig.counselorMessagesRead}/${conversationId}/read`);
}
