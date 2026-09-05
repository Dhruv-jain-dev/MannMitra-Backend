import { Mic, Send, ShieldCheck, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import PageTitle from "../components/PageTitle";
import ChatMessage from "../components/ChatMessage";
import { getAccessToken } from "../services/auth";
import {
  createConversation,
  getConversationAnalytics,
  getConversationMessages,
  getConversations,
  sendTextMessage,
  sendVoiceMessage
} from "../services/mannmitra";

const welcomeMessage = { role: "assistant", text: "Hi. I'm MannMitra. You can tell me what's on your mind, in your own words." };

function requestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function encodeWav(chunks, sampleRate) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const write = (offset, value) => view.setUint8(offset, value.charCodeAt(0));
  ["RIFF", "WAVE", "fmt ", "data"].forEach((value, index) => value.split("").forEach((char, charIndex) => write([0, 8, 12, 36][index] + charIndex, char)));
  view.setUint32(4, 36 + length * 2, true);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  view.setUint32(40, length * 2, true);
  let offset = 44;
  chunks.forEach(chunk => chunk.forEach(sample => {
    view.setInt16(offset, Math.max(-1, Math.min(1, sample)) * 0x7fff, true);
    offset += 2;
  }));
  return new Blob([buffer], { type: "audio/wav" });
}

function errorMessage(error) {
  return error.response?.data?.detail || error.message || "MannMitra could not process that request.";
}

function safetyPathway(risk) {
  if (!risk) return "Send a message to see MannMitra's saved wellbeing signals and safety guidance.";
  if (risk.is_crisis || risk.tier === "RED") return "Immediate support is recommended. Please contact a trusted person, campus support, or emergency services if you may be in danger.";
  if (risk.tier === "YELLOW") return "MannMitra has detected elevated distress. Consider a gentle coping step and reaching out to available support.";
  return "MannMitra is monitoring this conversation for changes and can offer supportive next steps when needed.";
}

export default function MannMitra() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [text, setText] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState("");
  const recorder = useRef(null);

  useEffect(() => () => {
    recorder.current?.stream?.getTracks().forEach(track => track.stop());
    recorder.current?.context?.close();
  }, []);

  const loadConversations = async () => {
    if (!getAccessToken()) return;
    const response = await getConversations();
    setConversations(response.data);
    return response.data;
  };

  const loadAnalytics = async id => {
    const response = await getConversationAnalytics(id);
    setAnalytics(response.data);
  };

  useEffect(() => {
    loadConversations()
      .then(items => items?.[0] && selectConversation(items[0].id))
      .catch(loadError => setError(errorMessage(loadError)));
  }, []);

  const selectConversation = async id => {
    if (!id) {
      setConversationId(null);
      setMessages([welcomeMessage]);
      setAnalytics(null);
      setError("");
      return;
    }
    setIsLoadingHistory(true);
    setError("");
    try {
      const [messagesResponse, analyticsResponse] = await Promise.all([
        getConversationMessages(id),
        getConversationAnalytics(id)
      ]);
      setConversationId(id);
      setMessages(messagesResponse.data.length ? messagesResponse.data.map(message => ({
        role: message.role,
        text: message.content,
        analysis: message.analysis
      })) : [welcomeMessage]);
      setAnalytics(analyticsResponse.data);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const response = await createConversation();
    setConversationId(response.data.id);
    setConversations(current => [response.data, ...current]);
    return response.data.id;
  };

  const addBackendResponse = data => {
    setMessages(current => [...current, { role: "assistant", text: data.assistant_response, analysis: data }]);
  };

  const sendText = async () => {
    const next = text.trim();
    if (!next || isSending || isLoadingHistory) return;
    if (!getAccessToken()) {
      setError("MannMitra requires a signed-in backend session. Please sign in again.");
      return;
    }
    setError("");
    setMessages(current => [...current, { role: "user", text: next }]);
    setText("");
    setIsSending(true);
    try {
      const isNewConversation = !conversationId;
      const id = await ensureConversation();
      const response = await sendTextMessage({ conversation_id: id, request_id: requestId(), text: next });
      addBackendResponse(response.data);
      await loadAnalytics(id);
      if (isNewConversation) await loadConversations();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsSending(false);
    }
  };

  const startRecording = async () => {
    if (!getAccessToken()) {
      setError("MannMitra requires a signed-in backend session. Please sign in again.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks = [];
      processor.onaudioprocess = event => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      source.connect(processor);
      processor.connect(context.destination);
      recorder.current = { stream, context, source, processor, chunks };
      setError("");
      setIsRecording(true);
    } catch {
      setError("Microphone access is required to record a voice message.");
    }
  };

  const stopAndSendRecording = async () => {
    const activeRecorder = recorder.current;
    if (!activeRecorder || isSending) return;
    activeRecorder.source.disconnect();
    activeRecorder.processor.disconnect();
    activeRecorder.stream.getTracks().forEach(track => track.stop());
    const sampleRate = activeRecorder.context.sampleRate;
    await activeRecorder.context.close();
    recorder.current = null;
    setIsRecording(false);
    const audio = new File([encodeWav(activeRecorder.chunks, sampleRate)], `mannmitra-${Date.now()}.wav`, { type: "audio/wav" });
    if (!audio.size) {
      setError("The recording was empty. Please try again.");
      return;
    }
    setError("");
    setIsSending(true);
    try {
      const isNewConversation = !conversationId;
      const id = await ensureConversation();
      const response = await sendVoiceMessage({ conversationId: id, requestId: requestId(), audio });
      setMessages(current => [...current, { role: "user", text: response.data.voice.transcript, analysis: response.data }]);
      addBackendResponse(response.data);
      await loadAnalytics(id);
      if (isNewConversation) await loadConversations();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsSending(false);
    }
  };

  const latest = analytics?.latest;
  const latestVoice = analytics?.latest_voice;
  const riskScore = typeof latest?.risk?.score === "number" ? latest.risk.score.toFixed(2) : null;

  return <><PageTitle eyebrow="MANNMITRA COMPANION" title="A space to talk, without judgement." subtitle="Private text and voice conversations are processed by MannMitra's backend safety and support pipeline." /><div className="chat-layout"><div className="card chat-card"><div className="chat-head"><div className="feature-icon"><Sparkles /></div><div><b>MannMitra</b><span>{isRecording ? "Recording voice message…" : isLoadingHistory ? "Loading conversation…" : isSending ? "Responding…" : "Text + voice ready"}</span></div><span className="privacy-tag"><ShieldCheck size={10}/> PRIVATE BY DESIGN</span></div><div className="chat-messages">{messages.map((message, index) => <ChatMessage key={index} {...message} />)}{error && <div className="small-muted">{error}</div>}</div><div className="chat-input"><button className="icon-btn" title={isRecording ? "Stop and send voice message" : "Record voice message"} onClick={isRecording ? stopAndSendRecording : startRecording} disabled={isSending || isLoadingHistory}><Mic size={17} />{isRecording ? "Stop" : "Voice"}</button><input value={text} onChange={event => setText(event.target.value)} onKeyDown={event => event.key === "Enter" && sendText()} placeholder="Type what you're feeling..." disabled={isSending || isLoadingHistory} /><button className="icon-btn" title="Text to speech"><Volume2 size={17} /></button><button className="btn btn-primary" onClick={sendText} disabled={isSending || isLoadingHistory}><Send size={15} /></button></div></div><aside className="card companion-side"><span className="eyebrow">CONVERSATION</span><h2>Continue where you left off.</h2><label><select value={conversationId || ""} onChange={event => selectConversation(event.target.value)} disabled={isSending || isLoadingHistory}><option value="">New conversation</option>{conversations.map(conversation => <option key={conversation.id} value={conversation.id}>{conversation.title || "Untitled conversation"}</option>)}</select></label><span className="eyebrow">LATEST SIGNALS</span>{isLoadingHistory ? <p>Loading saved conversation signals…</p> : latest ? <><div className="secure-note"><ShieldCheck size={15} /><span>Risk: {latest.risk?.tier || "Unknown"}{riskScore ? ` (${riskScore})` : ""}</span></div><div className="secure-note"><ShieldCheck size={15} /><span>Emotion: {latest.emotion?.label || "Unknown"}</span></div>{latestVoice && <div className="secure-note"><ShieldCheck size={15} /><span>Voice: {latestVoice.vocal_tone || "Unknown"}{typeof latestVoice.acoustic_stress === "number" ? ` · stress ${latestVoice.acoustic_stress.toFixed(1)}/100` : ""}</span></div>}{latest.rag?.is_used && <div className="secure-note"><ShieldCheck size={15} /><span>Support guidance used{latest.rag.sources?.length ? `: ${latest.rag.sources.join(", ")}` : ""}</span></div>}</> : <p>No saved signals yet. Send a message to begin.</p>}<span className="eyebrow">SAFETY PATHWAY</span><div className="secure-note"><ShieldCheck size={15} /><span>{safetyPathway(latest?.risk)}</span></div></aside></div></>;
}
