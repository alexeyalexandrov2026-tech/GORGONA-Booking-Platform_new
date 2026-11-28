"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import {
  createInboxThread,
  fetchInboxCalls,
  fetchInboxChannels,
  fetchInboxThreads,
  fetchThreadMessages,
  patchInboxThread,
  recordInboxCall,
  rotateInboxChannelToken,
  sendThreadMessage,
  upsertInboxChannel,
  type CallDirection,
  type CallDisposition,
  type CallStatus,
  type ChannelType,
  type InboxCallLog,
  type InboxChannel,
  type InboxMessage,
  type InboxThread,
  type MessageChannelType,
  type ThreadPriority,
  type ThreadStatus,
} from "../lib/omnichannel-api";

type TabId = "inbox" | "pbx" | "channels";

const CHANNEL_LABELS: Record<MessageChannelType, string> = {
  email: "Email",
  voice_pbx: "Virtual PBX",
  sms: "SMS",
  whatsapp: "WhatsApp",
  web_chat: "Web Chat",
  internal_note: "Internal Note",
};

function fmtDur(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Operation failed.";
}

export function OmnichannelInbox({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<TabId>("inbox");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [channels, setChannels] = useState<InboxChannel[]>([]);
  const [threads, setThreads] = useState<InboxThread[]>([]);
  const [calls, setCalls] = useState<InboxCallLog[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string>("");
  const [messages, setMessages] = useState<InboxMessage[]>([]);

  // Filter state
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // New conversation form
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newChannel, setNewChannel] = useState<ChannelType>("email");
  const [newSubject, setNewSubject] = useState("");
  const [newPriority, setNewPriority] = useState<ThreadPriority>("normal");
  const [newBody, setNewBody] = useState("");
  const [creatingThread, setCreatingThread] = useState(false);

  // Reply composer
  const [replyChannel, setReplyChannel] = useState<MessageChannelType>("email");
  const [replyBody, setReplyBody] = useState("");
  const [sendingReply, setSendingReply] = useState(false);

  // Virtual PBX call logger
  const [callDir, setCallDir] = useState<CallDirection>("outbound");
  const [callContact, setCallContact] = useState("");
  const [callPhone, setCallPhone] = useState("");
  const [callStatus, setCallStatus] = useState<CallStatus>("completed");
  const [callMinutes, setCallMinutes] = useState("4");
  const [callQueue, setCallQueue] = useState("Sales Desk · Ext 101");
  const [callDisp, setCallDisp] = useState<CallDisposition>("quote_requested");
  const [callSummary, setCallSummary] = useState("");
  const [savingCall, setSavingCall] = useState(false);

  // Channel setup form
  const [chType, setChType] = useState<ChannelType>("whatsapp");
  const [chName, setChName] = useState("WhatsApp Client Desk");
  const [chAddr, setChAddr] = useState("+1-312-555-0190");
  const [chMode, setChMode] = useState<"built_in" | "optional_byok">(
    "built_in",
  );
  const [chProvider, setChProvider] = useState("AMARKAL Messenger Gateway");
  const [savingChannel, setSavingChannel] = useState(false);
  const [latestWebhookToken, setLatestWebhookToken] = useState<{
    channel: string;
    token: string;
  } | null>(null);

  // Accessible label IDs
  const filterChId = useId();
  const filterStId = useId();
  const filterSearchId = useId();
  const newNameId = useId();
  const newEmailId = useId();
  const newPhoneId = useId();
  const newChId = useId();
  const newSubjId = useId();
  const newPriId = useId();
  const newBodyId = useId();
  const replyChId = useId();
  const replyBodyId = useId();
  const callDirId = useId();
  const callContactId = useId();
  const callPhoneId = useId();
  const callStId = useId();
  const callMinId = useId();
  const callQueueId = useId();
  const callDispId = useId();
  const callSumId = useId();
  const chTypeId = useId();
  const chNameId = useId();
  const chAddrId = useId();
  const chModeId = useId();
  const chProvId = useId();

  const reloadAll = useCallback(async () => {
    const [ch, th, cl] = await Promise.all([
      fetchInboxChannels(businessId),
      fetchInboxThreads(businessId),
      fetchInboxCalls(businessId),
    ]);
    setChannels(ch);
    setThreads(th);
    setCalls(cl);
    const first = th[0];
    if (first) {
      setSelectedThreadId((cur) => cur || first.id);
    }
  }, [businessId]);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        await reloadAll();
      } catch (err) {
        if (active) setError(errText(err));
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [reloadAll]);

  useEffect(() => {
    if (!selectedThreadId) return;
    let active = true;
    async function loadMsgs() {
      try {
        const list = await fetchThreadMessages(businessId, selectedThreadId);
        if (active) {
          setMessages(list);
          setThreads((prev) =>
            prev.map((t) =>
              t.id === selectedThreadId ? { ...t, unread_count: 0 } : t,
            ),
          );
        }
      } catch (err) {
        if (active) setError(errText(err));
      }
    }
    void loadMsgs();
    return () => {
      active = false;
    };
  }, [businessId, selectedThreadId]);

  const visibleThreads = threads.filter((t) => {
    if (channelFilter !== "all" && t.primary_channel !== channelFilter)
      return false;
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    const q = searchQuery.trim().toLowerCase();
    if (
      q &&
      !`${t.contact_name} ${t.contact_email ?? ""} ${t.subject} ${t.last_message_preview}`
        .toLowerCase()
        .includes(q)
    ) {
      return false;
    }
    return true;
  });

  const activeThread =
    threads.find((t) => t.id === selectedThreadId) ?? visibleThreads[0] ?? null;

  async function onCreateThread(e: React.FormEvent) {
    e.preventDefault();
    setCreatingThread(true);
    setError(null);
    setNotice(null);
    try {
      const res = await createInboxThread(businessId, {
        contact_name: newName.trim(),
        contact_email: newEmail.trim() || null,
        contact_phone: newPhone.trim() || null,
        primary_channel: newChannel,
        subject: newSubject.trim() || `Conversation with ${newName.trim()}`,
        priority: newPriority,
        initial_body: newBody.trim() || null,
      });
      await reloadAll();
      setSelectedThreadId(res.thread.id);
      setNewName("");
      setNewEmail("");
      setNewPhone("");
      setNewSubject("");
      setNewBody("");
      setNotice(
        `Conversation started with ${res.thread.contact_name} via ${CHANNEL_LABELS[res.thread.primary_channel]}.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setCreatingThread(false);
    }
  }

  async function onSendReply(e: React.FormEvent) {
    e.preventDefault();
    if (!activeThread || !replyBody.trim()) return;
    setSendingReply(true);
    setError(null);
    setNotice(null);
    try {
      const res = await sendThreadMessage(businessId, activeThread.id, {
        channel_type: replyChannel,
        direction: replyChannel === "internal_note" ? "internal" : "outbound",
        subject: activeThread.subject,
        body: replyBody.trim(),
      });
      setMessages((prev) => [...prev, res.message]);
      setThreads((prev) =>
        prev.map((t) => (t.id === res.thread.id ? res.thread : t)),
      );
      setReplyBody("");
      setNotice(
        replyChannel === "internal_note"
          ? "Internal team note saved to client timeline."
          : `Sent via ${CHANNEL_LABELS[replyChannel]} (${res.message.delivery_status}).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSendingReply(false);
    }
  }

  async function onChangeThreadStatus(threadId: string, status: ThreadStatus) {
    setError(null);
    try {
      const updated = await patchInboxThread(businessId, threadId, { status });
      setThreads((prev) =>
        prev.map((t) => (t.id === updated.id ? updated : t)),
      );
      setNotice(`Thread marked ${updated.status}.`);
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onRecordCall(e: React.FormEvent) {
    e.preventDefault();
    setSavingCall(true);
    setError(null);
    setNotice(null);
    try {
      const secs = Math.max(0, Math.round(Number(callMinutes || "0") * 60));
      const created = await recordInboxCall(businessId, {
        direction: callDir,
        caller_number:
          callDir === "outbound" ? "AMARKAL PBX" : callPhone.trim(),
        callee_number:
          callDir === "outbound" ? callPhone.trim() : "AMARKAL PBX",
        contact_name: callContact.trim(),
        call_status: callStatus,
        duration_seconds: secs,
        extension_or_queue: callQueue.trim(),
        transcript_summary: callSummary.trim(),
        disposition: callDisp,
      });
      await reloadAll();
      setCallContact("");
      setCallPhone("");
      setCallSummary("");
      setNotice(
        `Virtual PBX call with ${created.contact_name} logged and attached to their unified CRM thread.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingCall(false);
    }
  }

  async function onSaveChannel(e: React.FormEvent) {
    e.preventDefault();
    setSavingChannel(true);
    setError(null);
    setNotice(null);
    try {
      const res = await upsertInboxChannel(businessId, {
        channel_type: chType,
        display_name: chName.trim(),
        address_or_number: chAddr.trim(),
        mode: chMode,
        provider_label: chProvider.trim(),
        is_enabled: true,
        auto_greeting: "",
      });
      await reloadAll();
      if (res.webhook_token) {
        setLatestWebhookToken({
          channel: CHANNEL_LABELS[res.channel.channel_type],
          token: res.webhook_token,
        });
      }
      setNotice(`Channel "${res.channel.display_name}" saved.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingChannel(false);
    }
  }

  async function onRotateChannelToken(ch: InboxChannel) {
    setError(null);
    try {
      const res = await rotateInboxChannelToken(businessId, ch.channel_type);
      await reloadAll();
      if (res.webhook_token) {
        setLatestWebhookToken({
          channel: CHANNEL_LABELS[ch.channel_type],
          token: res.webhook_token,
        });
      }
      setNotice(
        `Rotated inbound webhook token for ${ch.display_name}. Copy it now — shown once.`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  const unreadTotal = threads.reduce((sum, t) => sum + t.unread_count, 0);
  const openThreadsCount = threads.filter((t) => t.status === "open").length;

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.6rem" }}>
            Omnichannel Unified Client Inbox &amp; Virtual PBX
          </h1>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            Read and reply to Client Emails, Virtual PBX calls &amp; voicemails,
            SMS, WhatsApp, and Web Chat from one timeline — built-in out of the
            box with optional BYOK connectors in App Hub.
          </p>
        </div>
      </div>

      {/* KPI Strip */}
      <div className="usr-grid">
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Open Conversations
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {openThreadsCount} ({unreadTotal} unread)
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Active Channels
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {channels.filter((c) => c.is_enabled).length} connected
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Virtual PBX Calls Logged
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {calls.length}
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Lock-In / Mandatory Add-Ons
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            $0 · Built-In
          </div>
        </div>
      </div>

      {/* Section Tabs */}
      <div
        role="tablist"
        aria-label="Omnichannel Inbox sections"
        className="usr-inline"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "inbox"}
          className={
            activeTab === "inbox" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("inbox")}
        >
          Unified Inbox ({threads.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "pbx"}
          className={
            activeTab === "pbx" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("pbx")}
        >
          Virtual PBX &amp; Calls ({calls.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "channels"}
          className={
            activeTab === "channels"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("channels")}
        >
          Channels &amp; Webhooks ({channels.length})
        </button>
      </div>

      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {notice}
        </p>
      )}
      {loading && (
        <p className="mgmt-loading" aria-live="polite">
          Loading Omnichannel Client Inbox…
        </p>
      )}

      {/* TAB 1: Unified Inbox */}
      {!loading && activeTab === "inbox" && (
        <div className="usr-stack">
          <section
            className="usr-card"
            aria-labelledby="inbox-workspace-heading"
          >
            <h2 id="inbox-workspace-heading" style={{ margin: "0 0 12px" }}>
              Unified Client Conversations
            </h2>
            <div className="usr-grid" style={{ marginBottom: 14 }}>
              <label htmlFor={filterChId}>
                Channel
                <select
                  id={filterChId}
                  value={channelFilter}
                  onChange={(e) => setChannelFilter(e.target.value)}
                >
                  <option value="all">All Channels</option>
                  <option value="email">Email</option>
                  <option value="voice_pbx">Virtual PBX</option>
                  <option value="sms">SMS</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="web_chat">Web Chat</option>
                </select>
              </label>
              <label htmlFor={filterStId}>
                Status
                <select
                  id={filterStId}
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">All Statuses</option>
                  <option value="open">Open</option>
                  <option value="pending">Pending</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
              <label htmlFor={filterSearchId}>
                Search Client or Subject
                <input
                  id={filterSearchId}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Name, email, or message text…"
                />
              </label>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit, minmax(min(300px, 100%), 1fr))",
                gap: 16,
              }}
            >
              {/* Thread List */}
              <div className="usr-stack" style={{ alignContent: "start" }}>
                {visibleThreads.length === 0 ? (
                  <p className="usr-muted">
                    No conversations match this filter. Start a new email or
                    messenger thread below.
                  </p>
                ) : (
                  visibleThreads.map((t) => {
                    const isSelected = activeThread?.id === t.id;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setSelectedThreadId(t.id)}
                        style={{
                          display: "block",
                          textAlign: "left",
                          padding: 14,
                          borderRadius: 12,
                          border: isSelected
                            ? "2px solid #111111"
                            : "1px solid var(--line)",
                          background: isSelected ? "#f8fafc" : "#ffffff",
                          color: "#111111",
                          cursor: "pointer",
                          width: "100%",
                        }}
                      >
                        <div
                          className="usr-inline"
                          style={{
                            justifyContent: "space-between",
                            gap: 8,
                            marginBottom: 4,
                          }}
                        >
                          <strong>{t.contact_name}</strong>
                          <span
                            style={{
                              fontSize: "0.75rem",
                              padding: "2px 8px",
                              borderRadius: 999,
                              background: "#eef2f7",
                              color: "#111111",
                            }}
                          >
                            {CHANNEL_LABELS[t.primary_channel]} · {t.status}
                          </span>
                        </div>
                        <div style={{ fontSize: "0.88rem", fontWeight: 600 }}>
                          {t.subject || "(No subject)"}
                        </div>
                        <div
                          className="usr-muted"
                          style={{ fontSize: "0.82rem", marginTop: 4 }}
                        >
                          {t.last_message_preview || "No messages yet"}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              {/* Active Conversation Timeline + Reply */}
              <div
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 14,
                  padding: 16,
                  background: "#fafafa",
                  minWidth: 0,
                }}
              >
                {activeThread ? (
                  <div className="usr-stack">
                    <div
                      className="usr-inline"
                      style={{
                        justifyContent: "space-between",
                        gap: 8,
                        borderBottom: "1px solid var(--line)",
                        paddingBottom: 10,
                      }}
                    >
                      <div>
                        <strong>{activeThread.contact_name}</strong>
                        <div
                          className="usr-muted"
                          style={{ fontSize: "0.82rem" }}
                        >
                          {[
                            activeThread.contact_email,
                            activeThread.contact_phone,
                            activeThread.linked_entity_ref,
                          ]
                            .filter(Boolean)
                            .join(" · ") || "Direct CRM Thread"}
                        </div>
                      </div>
                      <div className="usr-inline" style={{ gap: 6 }}>
                        {activeThread.status !== "resolved" ? (
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() =>
                              void onChangeThreadStatus(
                                activeThread.id,
                                "resolved",
                              )
                            }
                          >
                            Mark Resolved
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() =>
                              void onChangeThreadStatus(activeThread.id, "open")
                            }
                          >
                            Reopen
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="usr-stack">
                      {messages.map((m) => (
                        <div
                          key={m.id}
                          style={{
                            padding: 12,
                            borderRadius: 10,
                            border: "1px solid var(--line)",
                            background:
                              m.channel_type === "internal_note"
                                ? "#fefce8"
                                : m.direction === "outbound"
                                  ? "#ffffff"
                                  : "#eff6ff",
                          }}
                        >
                          <div
                            className="usr-inline"
                            style={{
                              justifyContent: "space-between",
                              fontSize: "0.78rem",
                              marginBottom: 4,
                            }}
                          >
                            <strong>
                              {m.sender_name || "Participant"} ·{" "}
                              {CHANNEL_LABELS[m.channel_type]} ({m.direction})
                            </strong>
                            <span className="usr-muted">
                              {m.delivery_status}
                            </span>
                          </div>
                          <div
                            style={{
                              fontSize: "0.9rem",
                              whiteSpace: "pre-line",
                            }}
                          >
                            {m.body}
                          </div>
                        </div>
                      ))}
                    </div>

                    <form
                      onSubmit={(e) => void onSendReply(e)}
                      className="usr-stack"
                      style={{
                        borderTop: "1px solid var(--line)",
                        paddingTop: 12,
                      }}
                    >
                      <label htmlFor={replyChId}>
                        Reply Channel
                        <select
                          id={replyChId}
                          value={replyChannel}
                          onChange={(e) =>
                            setReplyChannel(
                              e.target.value as MessageChannelType,
                            )
                          }
                        >
                          <option value="email">
                            Email (Built-In Resend / SMTP)
                          </option>
                          <option value="sms">SMS</option>
                          <option value="whatsapp">WhatsApp</option>
                          <option value="web_chat">Portal Web Chat</option>
                          <option value="internal_note">
                            Internal Team Note (private)
                          </option>
                        </select>
                      </label>
                      <label htmlFor={replyBodyId}>
                        Message
                        <textarea
                          id={replyBodyId}
                          className="usr-textarea"
                          rows={3}
                          required
                          value={replyBody}
                          onChange={(e) => setReplyBody(e.target.value)}
                          placeholder="Write an email, SMS, WhatsApp reply, or internal CRM note…"
                        />
                      </label>
                      <div>
                        <button
                          type="submit"
                          className="usr-small-btn"
                          disabled={sendingReply}
                        >
                          {sendingReply ? "Sending…" : "Send Message"}
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <p className="usr-muted">
                    Select a client conversation on the left or compose a new
                    thread below.
                  </p>
                )}
              </div>
            </div>
          </section>

          <section className="usr-card" aria-labelledby="new-thread-heading">
            <h2 id="new-thread-heading" style={{ margin: "0 0 10px" }}>
              Compose New Client Email or Messenger Thread
            </h2>
            <form onSubmit={(e) => void onCreateThread(e)} className="usr-grid">
              <label htmlFor={newNameId}>
                Client / Contact Name
                <input
                  id={newNameId}
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Sarah Miller — Apex Logistics"
                />
              </label>
              <label htmlFor={newEmailId}>
                Client Email
                <input
                  id={newEmailId}
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="sarah@apexlogistics.us"
                />
              </label>
              <label htmlFor={newPhoneId}>
                Client Phone (SMS / WhatsApp / PBX)
                <input
                  id={newPhoneId}
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="+1-312-555-0144"
                />
              </label>
              <label htmlFor={newChId}>
                Channel
                <select
                  id={newChId}
                  value={newChannel}
                  onChange={(e) => setNewChannel(e.target.value as ChannelType)}
                >
                  <option value="email">Email (Built-In)</option>
                  <option value="sms">SMS</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="web_chat">Web Chat</option>
                </select>
              </label>
              <label htmlFor={newSubjId}>
                Subject
                <input
                  id={newSubjId}
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="Q4 Dedicated Freight Quote & Delivery Schedule"
                />
              </label>
              <label htmlFor={newPriId}>
                Priority
                <select
                  id={newPriId}
                  value={newPriority}
                  onChange={(e) =>
                    setNewPriority(e.target.value as ThreadPriority)
                  }
                >
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                  <option value="low">Low</option>
                </select>
              </label>
              <label htmlFor={newBodyId} style={{ gridColumn: "1 / -1" }}>
                Initial Message
                <textarea
                  id={newBodyId}
                  className="usr-textarea"
                  rows={3}
                  value={newBody}
                  onChange={(e) => setNewBody(e.target.value)}
                  placeholder="Hello Sarah, sharing the revised rate sheet directly from AMARKAL…"
                />
              </label>
              <div>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={creatingThread}
                >
                  {creatingThread ? "Sending…" : "+ Start Conversation"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {/* TAB 2: Virtual PBX & Calls */}
      {!loading && activeTab === "pbx" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="pbx-logger-heading">
            <h2 id="pbx-logger-heading" style={{ margin: "0 0 8px" }}>
              Built-In Virtual PBX Dialer &amp; Call / Voicemail Logger
            </h2>
            <p className="usr-muted" style={{ margin: "0 0 12px" }}>
              Log inbound, outbound, or voicemail calls across sales and
              dispatch extensions — every call automatically syncs into the
              client&apos;s unified CRM timeline.
            </p>
            <form onSubmit={(e) => void onRecordCall(e)} className="usr-grid">
              <label htmlFor={callDirId}>
                Call Direction
                <select
                  id={callDirId}
                  value={callDir}
                  onChange={(e) => setCallDir(e.target.value as CallDirection)}
                >
                  <option value="outbound">Outbound Call</option>
                  <option value="inbound">Inbound Call</option>
                  <option value="missed">Missed / Voicemail</option>
                </select>
              </label>
              <label htmlFor={callContactId}>
                Client / Caller Name
                <input
                  id={callContactId}
                  required
                  value={callContact}
                  onChange={(e) => setCallContact(e.target.value)}
                  placeholder="Marcus Reed — Midwest Steel"
                />
              </label>
              <label htmlFor={callPhoneId}>
                Phone Number (US E.164)
                <input
                  id={callPhoneId}
                  required
                  value={callPhone}
                  onChange={(e) => setCallPhone(e.target.value)}
                  placeholder="+1-312-555-0199"
                />
              </label>
              <label htmlFor={callStId}>
                Call Outcome
                <select
                  id={callStId}
                  value={callStatus}
                  onChange={(e) => setCallStatus(e.target.value as CallStatus)}
                >
                  <option value="completed">Completed</option>
                  <option value="voicemail">Voicemail</option>
                  <option value="missed">Missed</option>
                </select>
              </label>
              <label htmlFor={callMinId}>
                Duration (minutes)
                <input
                  id={callMinId}
                  type="number"
                  step="0.5"
                  min="0"
                  value={callMinutes}
                  onChange={(e) => setCallMinutes(e.target.value)}
                />
              </label>
              <label htmlFor={callQueueId}>
                PBX Extension / Queue
                <input
                  id={callQueueId}
                  value={callQueue}
                  onChange={(e) => setCallQueue(e.target.value)}
                />
              </label>
              <label htmlFor={callDispId}>
                CRM Disposition
                <select
                  id={callDispId}
                  value={callDisp}
                  onChange={(e) =>
                    setCallDisp(e.target.value as CallDisposition)
                  }
                >
                  <option value="quote_requested">Quote Requested</option>
                  <option value="follow_up">Follow-Up Needed</option>
                  <option value="resolved">Resolved</option>
                  <option value="support_ticket">Support Ticket</option>
                  <option value="voicemail_left">Voicemail Left</option>
                </select>
              </label>
              <label htmlFor={callSumId} style={{ gridColumn: "1 / -1" }}>
                Call Notes / Voicemail Transcript Summary
                <textarea
                  id={callSumId}
                  className="usr-textarea"
                  rows={2}
                  value={callSummary}
                  onChange={(e) => setCallSummary(e.target.value)}
                  placeholder="Client confirmed 2-truck weekly reefer route Chicago -> Dallas starting Monday."
                />
              </label>
              <div>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingCall}
                >
                  {savingCall ? "Logging…" : "+ Log PBX Call & Sync to Inbox"}
                </button>
              </div>
            </form>
          </section>

          <section className="usr-card" aria-labelledby="pbx-history-heading">
            <h2 id="pbx-history-heading" style={{ margin: "0 0 10px" }}>
              Recent Virtual PBX Call History ({calls.length})
            </h2>
            {calls.length === 0 ? (
              <p className="usr-muted">No Virtual PBX calls recorded yet.</p>
            ) : (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Virtual PBX call history table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Direction</th>
                      <th>Contact</th>
                      <th>Extension / Queue</th>
                      <th>Duration</th>
                      <th>Disposition</th>
                      <th>Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calls.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <strong>{c.direction}</strong> ({c.call_status})
                        </td>
                        <td>
                          <strong>{c.contact_name}</strong>
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.8rem" }}
                          >
                            {c.direction === "outbound"
                              ? c.callee_number
                              : c.caller_number}
                          </div>
                        </td>
                        <td>{c.extension_or_queue}</td>
                        <td>{fmtDur(c.duration_seconds)}</td>
                        <td>{c.disposition}</td>
                        <td>{c.transcript_summary || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: Channels & Webhooks */}
      {!loading && activeTab === "channels" && (
        <div className="usr-stack">
          {latestWebhookToken && (
            <section
              className="usr-card"
              role="status"
              style={{ borderColor: "#111111", background: "#f8fafc" }}
            >
              <strong>
                One-Time Inbound Webhook Token ({latestWebhookToken.channel})
              </strong>
              <p className="usr-muted" style={{ margin: "4px 0 8px" }}>
                Forward inbound Email, WhatsApp, SMS, or SIP PBX events to{" "}
                <code>POST /v1/public/inbox/inbound</code> with header{" "}
                <code>X-AMARKAL-Inbox-Token</code>:
              </p>
              <code
                style={{
                  display: "block",
                  padding: "8px 10px",
                  background: "#ffffff",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  wordBreak: "break-all",
                }}
              >
                {latestWebhookToken.token}
              </code>
            </section>
          )}

          <section className="usr-card" aria-labelledby="channels-list-heading">
            <div
              className="usr-inline"
              style={{ justifyContent: "space-between", marginBottom: 12 }}
            >
              <div>
                <h2 id="channels-list-heading" style={{ margin: 0 }}>
                  Connected Communication Channels ({channels.length})
                </h2>
                <p className="usr-muted" style={{ margin: "4px 0 0" }}>
                  Email, Virtual PBX, and Web Chat work out of the box. Connect
                  optional Microsoft 365, Google Workspace, or Twilio BYOK keys
                  anytime in App Hub without lock-in.
                </p>
              </div>
              <Link
                href="/integrations/"
                className="button secondary usr-small-btn"
              >
                Open Optional BYOK Connectors (App Hub) ↗
              </Link>
            </div>

            <div
              style={{ overflowX: "auto", marginBottom: 18 }}
              tabIndex={0}
              role="region"
              aria-label="Communication channels table"
            >
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Address / Number</th>
                    <th>Mode</th>
                    <th>Provider</th>
                    <th>Inbound Webhook</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((ch) => (
                    <tr key={ch.id}>
                      <td>
                        <strong>{ch.display_name}</strong>
                      </td>
                      <td>
                        <code>{ch.address_or_number || "Built-in"}</code>
                      </td>
                      <td>{ch.mode}</td>
                      <td>{ch.provider_label}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary usr-small-btn"
                          onClick={() => void onRotateChannelToken(ch)}
                        >
                          Rotate Token ({ch.webhook_token_prefix ?? "new"}…)
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ margin: "0 0 10px" }}>
              Add or Update Messaging Channel (WhatsApp / SMS / Email / PBX)
            </h3>
            <form onSubmit={(e) => void onSaveChannel(e)} className="usr-grid">
              <label htmlFor={chTypeId}>
                Channel Type
                <select
                  id={chTypeId}
                  value={chType}
                  onChange={(e) => setChType(e.target.value as ChannelType)}
                >
                  <option value="whatsapp">WhatsApp Business</option>
                  <option value="sms">SMS Messenger</option>
                  <option value="email">Client Email</option>
                  <option value="voice_pbx">Virtual PBX</option>
                  <option value="web_chat">Portal Web Chat</option>
                </select>
              </label>
              <label htmlFor={chNameId}>
                Display Name
                <input
                  id={chNameId}
                  required
                  value={chName}
                  onChange={(e) => setChName(e.target.value)}
                />
              </label>
              <label htmlFor={chAddrId}>
                Email Address or US Phone Number
                <input
                  id={chAddrId}
                  value={chAddr}
                  onChange={(e) => setChAddr(e.target.value)}
                />
              </label>
              <label htmlFor={chModeId}>
                Routing Mode
                <select
                  id={chModeId}
                  value={chMode}
                  onChange={(e) =>
                    setChMode(e.target.value as "built_in" | "optional_byok")
                  }
                >
                  <option value="built_in">Built-In AMARKAL Gateway</option>
                  <option value="optional_byok">
                    Optional BYOK (M365 / Twilio / Meta)
                  </option>
                </select>
              </label>
              <label htmlFor={chProvId}>
                Provider Label
                <input
                  id={chProvId}
                  value={chProvider}
                  onChange={(e) => setChProvider(e.target.value)}
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingChannel}
                >
                  {savingChannel ? "Saving…" : "Save Channel"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
