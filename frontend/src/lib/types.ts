// Shared types for the refund agent UI. Discriminated unions everywhere so
// rendering can switch exhaustively without `any`.

export type Role = "customer" | "admin" | "superuser";

export interface Session {
  token: string;
  username: string;
  role: Role;
  has_customer_profile: boolean;
}

export type Decision = "approved" | "rejected" | "pending_review";

export interface Candidate {
  order_ref: string;
  item_name: string;
  amount: number;
  purchase_date: string;
}

// ---- Chat messages rendered in the center panel ----
// Progress steps are NOT persisted as messages; they stream transiently while
// the agent works and then collapse into the assistant message's `steps`
// (an expandable "reasoning" trail, ChatGPT-style).
export type ChatMessage =
  | { kind: "user"; text: string }
  | {
      kind: "assistant";
      text: string;
      decision?: Decision | null;
      rule?: string | null;
      steps?: string[];
      candidates?: Candidate[];
    };

// ---- Trace events rendered in the admin panel ----
export type TraceEvent =
  | {
      kind: "node";
      node: string;
      label: string;
      detail: string;
      data: Record<string, unknown>;
      elapsed_ms: number;
    }
  | { kind: "security_alert"; detail: string; sample: string }
  | {
      kind: "summary";
      total_ms: number;
      decision: Decision | null;
      rule: string | null;
      used_llm: boolean;
    }
  | { kind: "error"; detail: string };

