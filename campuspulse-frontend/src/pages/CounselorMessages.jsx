import { MessageCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";
import PageTitle from "../components/PageTitle";
import { getCounselorMessages, markCounselorMessagesRead, sendCounselorMessage } from "../services/counselor";

export default function CounselorMessages() {
  const [threads, setThreads] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const selected = threads.find(thread => thread.id === selectedId) || threads[0];

  const load = async () => {
    setLoading(true); setError("");
    try {
      const response = await getCounselorMessages();
      const items = response.data.items || [];
      setThreads(items);
      setSelectedId(current => current || items[0]?.id || "");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || "Unable to load messages.");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const selectThread = async id => {
    setSelectedId(id);
    const thread = threads.find(item => item.id === id);
    if (thread?.unread_count) {
      try { await markCounselorMessagesRead(id); await load(); } catch { /* history remains available */ }
    }
  };
  const send = async () => {
    const content = draft.trim();
    if (!content || !selected || sending) return;
    setSending(true); setError("");
    try { await sendCounselorMessage({ conversation_id: selected.id, content }); setDraft(""); await load(); }
    catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || "Unable to send message."); }
    finally { setSending(false); }
  };

  return <>
    <PageTitle eyebrow="COUNSELOR CENTER" title="Messages from assigned students." subtitle="Respond only within counselor-student relationships assigned to your account." />
    {loading ? <State text="Loading messages…" /> : error && !threads.length ? <State text={error} action={<button className="btn btn-soft" onClick={load}>Try again</button>} /> : <div className="counselor-dashboard-grid">
      <section className="card counselor-panel"><div className="card-top"><div><span className="eyebrow">CONVERSATIONS</span><h2>Assigned student messages</h2></div><MessageCircle size={20} /></div>{threads.length ? <div className="task-list">{threads.map(thread => <button className="message-thread-row" key={thread.id} onClick={() => selectThread(thread.id)}><span><b>{thread.student_id}</b><small>{thread.unread_count ? `${thread.unread_count} unread` : "Read"}</small></span><small>{thread.updated_at ? new Date(thread.updated_at).toLocaleString() : ""}</small></button>)}</div> : <div className="empty-state"><MessageCircle size={24}/><h3>No messages yet</h3><p>Messages from assigned students will appear here.</p></div>}</section>
      {selected && <section className="card counselor-panel"><div className="card-top"><div><span className="eyebrow">MESSAGE HISTORY</span><h2>{selected.student_id}</h2></div></div><div className="message-history">{selected.messages?.length ? selected.messages.map(message => <div className={`message-bubble ${message.sender_role === "counselor" ? "outgoing" : "incoming"}`} key={message.id}><p>{message.content}</p><small>{new Date(message.created_at).toLocaleString()}</small></div>) : <p className="small-muted">No messages yet.</p>}</div><div className="message-compose"><textarea value={draft} onChange={event => setDraft(event.target.value)} maxLength={5000} rows={2} placeholder="Write a reply…"/><button className="btn btn-primary" onClick={send} disabled={!draft.trim() || sending}>{sending ? "Sending…" : "Send"} <Send size={14}/></button></div>{error && <p className="small-muted">{error}</p>}</section>}
    </div>}
  </>;
}

function State({ text, action }) { return <div className="card placeholder-panel"><p>{text}</p>{action}</div>; }
