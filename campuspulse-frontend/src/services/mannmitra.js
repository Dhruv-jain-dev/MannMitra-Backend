import { api, apiConfig } from "./api";

export async function createConversation() {
  return api.post(apiConfig.conversations, {});
}

export async function getConversations() {
  return api.get(apiConfig.conversations);
}

export async function getConversationMessages(conversationId) {
  return api.get(`${apiConfig.conversations}/${conversationId}/messages`);
}

export async function getConversationAnalytics(conversationId) {
  return api.get(`${apiConfig.conversations}/${conversationId}/analytics`);
}

export async function sendTextMessage(payload) {
  return api.post(apiConfig.mannmitraText, payload);
}

export async function sendVoiceMessage({ conversationId, requestId, audio }) {
  const formData = new FormData();
  formData.append("conversation_id", conversationId);
  formData.append("request_id", requestId);
  formData.append("audio", audio, audio.name || "recording.wav");

  return api.post(apiConfig.mannmitraVoice, formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
}
