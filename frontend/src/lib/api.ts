// API client: REST for auth/telemetry, manual fetch-stream parser for the
// dual-channel SSE chat endpoint (EventSource can't POST a body, so we read
// the ReadableStream ourselves and split SSE frames by hand).

import type { Session, TraceEvent } from "./types";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Thrown when the server rejects the token (401) — the UI should sign out.
export class AuthError extends Error {}
// Thrown when the backend is unreachable (network/CORS/connection dropped).
export class NetworkError extends Error {}

export async function login(
  username: string,
  password: string,
): Promise<Session> {
  const res = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(detail.detail || "Login failed");
  }
  return res.json();
}

export async function fetchTelemetry(token: string): Promise<TelemetryPayload> {
  const res = await fetch(`${API}/api/admin/telemetry`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load telemetry");
  return res.json();
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export async function listConversations(
  token: string,
): Promise<ConversationSummary[]> {
  let res: Response;
  try {
    res = await fetch(`${API}/api/conversations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new NetworkError("Could not reach the server");
  }
  if (res.status === 401) throw new AuthError("Session expired");
  if (!res.ok) return [];
  return res.json();
}

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  decision: string | null;
  rule: string | null;
  steps: string[];
}

export async function getConversationMessages(
  token: string,
  conversationId: string,
): Promise<StoredMessage[]> {
  let res: Response;
  try {
    res = await fetch(`${API}/api/conversations/${conversationId}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new NetworkError("Could not reach the server");
  }
  if (res.status === 401) throw new AuthError("Session expired");
  if (!res.ok) return [];
  return res.json();
}

export interface TelemetryPayload {
  totals: {
    tool_calls: number;
    avg_latency_ms: number;
    refunds_by_status: Record<string, number>;
  };
  recent_calls: Array<{
    id: number;
    tool: string;
    arguments: Record<string, unknown>;
    result: Record<string, unknown>;
    latency_ms: number;
    created_at: string;
  }>;
}

// Raw SSE frame as parsed off the wire: { event, data }.
export interface SseFrame {
  event: string;
  data: Record<string, unknown>;
}

// Open the chat stream and invoke onFrame for each parsed SSE frame.
export async function streamChat(
  token: string,
  message: string,
  conversationId: string | null,
  onFrame: (frame: SseFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message, conversation_id: conversationId }),
      signal,
    });
  } catch {
    // fetch rejects on network failure / connection drop ("Failed to fetch").
    throw new NetworkError("Could not reach the server");
  }

  if (res.status === 401) throw new AuthError("Session expired");
  if (!res.ok || !res.body) {
    const detail = await res
      .json()
      .catch(() => ({ detail: "Chat request failed" }));
    throw new Error(detail.detail || "Chat request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // Normalize CRLF -> LF: sse-starlette emits \r\n line endings and
    // \r\n\r\n frame separators; splitting on "\n\n" alone would leave
    // stray \r and mis-frame the stream.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const raw of frames) {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length === 0) continue;
      try {
        onFrame({ event, data: JSON.parse(dataLines.join("\n")) });
      } catch {
        // ignore malformed frame
      }
    }
  }
}
