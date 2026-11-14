import { ArrowRight, HeartHandshake, Phone, Send, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getCounselorContacts, getCounselorMessages, markCounselorMessagesRead, sendCounselorMessage } from "../services/counselor";

export default function CounselorConnect() {
  const [contacts, setContacts] = useState([]);
  const [threads, setThreads] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const loadMessaging = async () => {
    setLoading(true); setError("");
    try {
      const [contactsResponse, messagesResponse] = await Promise.all([getCounselorContacts(), getCounselorMessages()]);
      setContacts(contactsResponse.data);
      setThreads(messagesResponse.data.items || []);
      setSelectedId(current => current || contactsResponse.data[0]?.id || "");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || "Unable to load counselor messaging.");
    } finally { setLoading(false); }
  };
  useEffect(() => { loadMessaging(); }, []);

  const selectedThread = useMemo(() => threads.find(thread => thread.counselor_id === selectedId), [threads, selectedId]);
  const sendMessage = async () => {
    const content = draft.trim();
    if (!content || !selectedId || sending) return;
    setSending(true); setError("");
    try {
      await sendCounselorMessage({ counselor_id: selectedId, conversation_id: selectedThread?.id, content });
      setDraft("");
      const response = await getCounselorMessages();
      setThreads(response.data.items || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || "Unable to send your message.");
    } finally { setSending(false); }
  };
  const selectCounselor = async id => {
    setSelectedId(id);
    const thread = threads.find(item => item.counselor_id === id);
    if (thread?.unread_count) {
      try { await markCounselorMessagesRead(thread.id); } catch { /* history remains visible if read marking is unavailable */ }
    }
  };

  return <section className="support-hub">
    <div className="support-hub-heading"><div><span className="eyebrow">SUPPORT HUB</span><h2>Support that feels easy to reach.</h2><p>Connect with an assigned counselor for planned support, or use immediate helplines when you need urgent help.</p></div><HeartHandshake size={27} /></div>
    <div className="support-hub-grid">
      <div className="support-panel card">
        <div className="panel-heading"><div><span className="section-label">CONNECT WITH A COUNSELOR</span><h3>Choose someone to contact.</h3></div><Users size={18} /></div>
        {loading ? <div className="empty-state"><p>Loading assigned counselors…</p></div> : error && !contacts.length ? <div className="empty-state"><p>{error}</p><button className="btn btn-soft" onClick={loadMessaging}>Try again</button></div> : <div className="counselor-list">
          {contacts.map(contact => <article className={`counselor-card ${selectedId === contact.id ? "selected" : ""}`} key={contact.id}>
            <div className="counselor-avatar">C</div><div className="counselor-info"><h3>{contact.id}</h3><p>Assigned counselor</p><div className="counselor-meta"><span className="availability">Secure in-app messages</span><span>{threads.find(thread => thread.counselor_id === contact.id)?.unread_count || 0} unread</span></div></div><div className="counselor-actions"><button className="btn btn-soft" onClick={() => selectCounselor(contact.id)}>Message <ArrowRight size={14}/></button></div>
          </article>)}
          {!contacts.length && <div className="empty-state"><p>No counselor has been assigned to your account yet.</p></div>}
        </div>}
        {selectedId && <div className="card support-message-thread"><div className="panel-heading"><div><span className="section-label">MESSAGE HISTORY</span><h3>{selectedId}</h3></div></div><div className="message-history">{selectedThread?.messages?.length ? selectedThread.messages.map(message => <div className={`message-bubble ${message.sender_role === "student" ? "outgoing" : "incoming"}`} key={message.id}><p>{message.content}</p><small>{formatMessageDate(message.created_at)}</small></div>) : <p className="small-muted">No messages yet. Send a message to begin.</p>}</div><div className="message-compose"><textarea value={draft} onChange={event => setDraft(event.target.value)} maxLength={5000} rows={2} placeholder="Write a message to your counselor…"/><button className="btn btn-primary" onClick={sendMessage} disabled={!draft.trim() || sending}>{sending ? "Sending…" : "Send"} <Send size={14}/></button></div>{error && <p className="small-muted">{error}</p>}</div>}
        <p className="tiny-note">Only assigned counselor relationships can receive these messages. Emergency support remains available below.</p>
      </div>

      <div className="support-panel immediate-panel card"><div className="panel-heading"><div><span className="section-label">NEED IMMEDIATE SUPPORT?</span><h3>Help is available now.</h3></div><HeartHandshake size={18} /></div><div className="emergency-stack"><a className="emergency-card" href="tel:14416"><div className="emergency-icon"><HeartHandshake size={20} /></div><div><b>Tele-MANAS</b><p>24×7 mental-health counselling support.</p><strong>Call 14416</strong></div><Phone size={17} /></a><a className="emergency-card emergency-red" href="tel:112"><div className="emergency-icon"><Phone size={20} /></div><div><b>Emergency · 112</b><p>Urgent police, fire, medical or other emergency assistance.</p><strong>Call 112</strong></div><Phone size={17} /></a></div><div className="support-note"><HeartHandshake size={15} /><span>For urgent physical danger, use 112. For mental-health counselling support, use Tele-MANAS.</span></div></div>
    </div>
  </section>;
}

function formatMessageDate(value) { return new Date(value).toLocaleString(); }
