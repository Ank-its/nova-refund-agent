"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AuthError,
  getConversationMessages,
  listConversations,
  NetworkError,
  streamChat,
  type ConversationSummary,
  type SseFrame,
} from "@/lib/api";
import type { ChatMessage, Decision, Session, TraceEvent } from "@/lib/types";
import AdminPanel from "./AdminPanel";
import ChatPanel from "./ChatPanel";
import HistorySidebar from "./HistorySidebar";
import Topbar from "./Topbar";

export default function Dashboard({
  session,
  onLogout,
}: {
  session: Session;
  onLogout: () => void;
}) {
  const canViewAdmin = session.role === "admin" || session.role === "superuser";
  const canChat = session.has_customer_profile;

  const [adminOpen, setAdminOpen] = useState(canViewAdmin && !canChat);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [liveSteps, setLiveSteps] = useState<string[]>([]);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const [telemetryKey, setTelemetryKey] = useState(0);

  const stepsRef = useRef<string[]>([]);
  const activeIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load persisted conversations on login (survives logout/login & restarts).
  useEffect(() => {
    if (!canChat) return;
    listConversations(session.token)
      .then(setConversations)
      .catch((e) => {
        // A stale/forged token after a redeploy → bounce to login cleanly.
        if (e instanceof AuthError) onLogout();
      });
  }, [session.token, canChat, onLogout]);

  const setActive = useCallback((id: string | null) => {
    setActiveId(id);
    activeIdRef.current = id;
  }, []);

  const selectConversation = useCallback(
    async (id: string) => {
      setActive(id);
      setLiveTrace([]);
      let stored;
      try {
        stored = await getConversationMessages(session.token, id);
      } catch (e) {
        if (e instanceof AuthError) onLogout();
        return;
      }
      setMessages(
        stored.map((m) =>
          m.role === "user"
            ? { kind: "user", text: m.content }
            : {
                kind: "assistant",
                text: m.content,
                decision: (m.decision as Decision | null) ?? null,
                rule: m.rule,
                steps: m.steps ?? [],
              },
        ),
      );
    },
    [session.token, setActive, onLogout],
  );

  const newConversation = useCallback(() => {
    setActive(null);
    setMessages([]);
    setLiveTrace([]);
  }, [setActive]);

  const pushMessage = useCallback(
    (m: ChatMessage) => setMessages((prev) => [...prev, m]),
    [],
  );

  const handleFrame = useCallback((frame: SseFrame) => {
    const d = frame.data;
    if (frame.event === "meta") {
      const id = String(d.conversation_id);
      const title = String(d.title);
      activeIdRef.current = id;
      setActiveId(id);
      setConversations((prev) => {
        const exists = prev.find((c) => c.id === id);
        if (exists) return prev.map((c) => (c.id === id ? { ...c, title } : c));
        return [{ id, title, updated_at: "" }, ...prev];
      });
      return;
    }
    if (frame.event === "chat") {
      if (d.type === "progress") {
        stepsRef.current = [...stepsRef.current, String(d.text)];
        setLiveSteps(stepsRef.current);
      } else if (d.type === "message") {
        // Prefer the backend's gated steps (empty for greetings/small-talk);
        // fall back to the live-streamed steps if the field is absent.
        const finalSteps = Array.isArray(d.steps)
          ? (d.steps as unknown[]).map(String)
          : [...stepsRef.current];
        pushMessage({
          kind: "assistant",
          text: String(d.text),
          decision: (d.decision as Decision | null) ?? null,
          rule: (d.rule as string | null) ?? null,
          steps: finalSteps,
        });
        setLiveSteps([]);
      }
    } else if (frame.event === "trace") {
      const t = d.type;
      if (t === "node") {
        setLiveTrace((p) => [
          ...p,
          {
            kind: "node",
            node: String(d.node),
            label: String(d.label),
            detail: String(d.detail),
            data: (d.data as Record<string, unknown>) ?? {},
            elapsed_ms: Number(d.elapsed_ms ?? 0),
          },
        ]);
      } else if (t === "security_alert") {
        const sample = (d.data as { sample?: string } | undefined)?.sample ?? "";
        setLiveTrace((p) => [
          ...p,
          { kind: "security_alert", detail: String(d.detail), sample },
        ]);
      } else if (t === "summary") {
        setLiveTrace((p) => [
          ...p,
          {
            kind: "summary",
            total_ms: Number(d.total_ms ?? 0),
            decision: (d.decision as Decision | null) ?? null,
            rule: (d.rule as string | null) ?? null,
            used_llm: Boolean(d.used_llm),
          },
        ]);
      } else if (t === "error") {
        setLiveTrace((p) => [...p, { kind: "error", detail: String(d.detail) }]);
      }
    }
  }, [pushMessage]);

  const send = useCallback(
    async (text: string) => {
      pushMessage({ kind: "user", text });
      setBusy(true);
      stepsRef.current = [];
      setLiveSteps([]);
      setLiveTrace([]);
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      try {
        await streamChat(
          session.token,
          text,
          activeIdRef.current,
          handleFrame,
          abortRef.current.signal,
        );
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // superseded by a newer message — ignore
        } else if (err instanceof AuthError) {
          onLogout(); // token no longer valid → back to login
        } else if (err instanceof NetworkError) {
          pushMessage({
            kind: "assistant",
            text: "I couldn't reach the server just now. Please check your connection and try again.",
          });
        } else {
          pushMessage({
            kind: "assistant",
            text: "Sorry, something went wrong handling that request. Please try again.",
          });
        }
      } finally {
        setBusy(false);
        setLiveSteps([]);
        setTelemetryKey((k) => k + 1);
      }
    },
    [session.token, handleFrame, pushMessage, onLogout],
  );

  return (
    <div className="app-bg flex h-screen flex-col">
      <Topbar
        username={session.username}
        role={session.role}
        canViewAdmin={canViewAdmin}
        adminOpen={adminOpen}
        onToggleAdmin={() => setAdminOpen((v) => !v)}
        onLogout={onLogout}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: history — transparent, always visible, thin divider on the right */}
        <div className="hidden w-64 shrink-0 border-r border-black/5 md:block">
          <HistorySidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={selectConversation}
            onNew={newConversation}
          />
        </div>

        {/* Center: chat — full pane width; ChatPanel centers its own content and
            keeps the scrollbar at the pane's right edge. */}
        <main className="flex flex-1 flex-col overflow-hidden">
          <ChatPanel
            username={session.username}
            messages={messages}
            liveSteps={liveSteps}
            busy={busy}
            disabled={!canChat}
            disabledReason="This is an admin-only account. Chat is disabled — open the telemetry panel from the top bar."
            onSend={send}
          />
        </main>

        {/* Right: telemetry — optional */}
        {canViewAdmin && adminOpen && (
          <div className="hidden w-[34%] min-w-[330px] max-w-[460px] shrink-0 lg:block">
            <AdminPanel
              token={session.token}
              liveTrace={liveTrace}
              refreshKey={telemetryKey}
            />
          </div>
        )}
      </div>
    </div>
  );
}
