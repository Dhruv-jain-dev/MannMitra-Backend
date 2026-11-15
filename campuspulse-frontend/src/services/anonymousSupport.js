import { api, apiConfig } from "./api";

export const createAnonymousConversation = payload => api.post(apiConfig.anonymousSupport, payload);
export const getAnonymousConversations = () => api.get(apiConfig.anonymousSupport);
export const getAnonymousConversation = id => api.get(`${apiConfig.anonymousSupport}/${id}`);
export const sendAnonymousStudentMessage = (id, payload) => api.post(`${apiConfig.anonymousSupport}/${id}/messages`, payload);
export const closeAnonymousConversation = id => api.post(`${apiConfig.anonymousSupport}/${id}/close`);

export const getAnonymousCounselorInbox = () => api.get("/api/counselor/anonymous-support");
export const acceptAnonymousConversation = id => api.post(`/api/counselor/anonymous-support/${id}/accept`);
export const getAnonymousCounselorConversation = id => api.get(`/api/counselor/anonymous-support/${id}`);
export const sendAnonymousCounselorMessage = (id, payload) => api.post(`/api/counselor/anonymous-support/${id}/messages`, payload);
export const updateAnonymousConversation = (id, payload) => api.patch(`/api/counselor/anonymous-support/${id}`, payload);
export const addAnonymousNote = (id, payload) => api.post(`/api/counselor/anonymous-support/${id}/notes`, payload);
export const createAnonymousFollowup = (id, payload) => api.post(`/api/counselor/anonymous-support/${id}/followups`, payload);
