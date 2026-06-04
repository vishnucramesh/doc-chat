import { supabase } from "./supabase";

// `||` not `??` on purpose: `??` only falls back on null/undefined, so a
// misconfigured `VITE_API_BASE_URL=""` would leave BASE as an empty string
// and every fetch becomes a relative URL. `||` covers the empty-string case.
const BASE = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Pull a human-readable error string out of a non-2xx response.
 *
 * Handles three shapes:
 *   - FastAPI HTTPException:        { "detail": "message" }
 *   - FastAPI validation errors:    { "detail": [{ "msg": "...", "loc": [...] }, ...] }
 *   - Anything else (text/HTML/empty): falls back to the raw body or a status string.
 *
 * Critically, this never returns raw JSON to the UI — that was the bug before:
 * `uploadDocument` was throwing `await r.text()` directly, so users saw
 * `{"detail":"unsupported file type: .html"}` as the error.
 *
 * Response.text() can only be called once, so we read once then attempt JSON.
 */
async function parseApiError(r: Response): Promise<string> {
  let text = "";
  try {
    text = await r.text();
  } catch {
    return `Request failed (${r.status})`;
  }
  if (!text) return `Request failed (${r.status})`;

  try {
    const json: unknown = JSON.parse(text);
    if (json && typeof json === "object") {
      const detail = (json as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d)))
          .join("; ");
      }
    }
    if (typeof json === "string") return json;
  } catch {
    // not JSON — fall through and return the raw text
  }
  return text;
}

export interface Doc {
  id: string;
  filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  chunk_count: number;
  page_count: number | null;
  size_bytes: number | null;
  content_type: string | null;
  error: string | null;
  created_at: string;
}

export interface Citation {
  n: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  // Pages covered by this context window. Empty array if no page info
  // (e.g. .txt files). One element means a single page; multiple means
  // the window spans a page range (rendered as "pages N–M").
  pages: number[];
  snippet: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export async function listDocuments(): Promise<Doc[]> {
  const r = await fetch(`${BASE}/documents`, { headers: await authHeader() });
  if (!r.ok) throw new Error(await parseApiError(r));
  return r.json();
}

export async function uploadDocument(file: File): Promise<Doc> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE}/documents`, {
    method: "POST",
    headers: await authHeader(),
    body: fd,
  });
  if (!r.ok) throw new Error(await parseApiError(r));
  return r.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const r = await fetch(`${BASE}/documents/${id}`, {
    method: "DELETE",
    headers: await authHeader(),
  });
  if (!r.ok && r.status !== 204) throw new Error(await parseApiError(r));
}

export async function listConversations(): Promise<Conversation[]> {
  const r = await fetch(`${BASE}/conversations`, { headers: await authHeader() });
  if (!r.ok) throw new Error(await parseApiError(r));
  return r.json();
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const r = await fetch(`${BASE}/conversations/${id}`, { headers: await authHeader() });
  if (!r.ok) throw new Error(await parseApiError(r));
  return r.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const r = await fetch(`${BASE}/conversations/${id}`, {
    method: "DELETE",
    headers: await authHeader(),
  });
  if (!r.ok && r.status !== 204) throw new Error(await parseApiError(r));
}

// SSE-style event for chat streaming
export type ChatEvent =
  | { type: "meta"; conversation_id: string; citations: Citation[]; retrieval_ms: number; retrieved_count: number }
  | { type: "token"; text: string }
  | { type: "done"; retrieval_ms: number; generation_ms: number }
  | { type: "error"; message: string };

export async function streamChat(
  body: { message: string; conversation_id?: string | null; document_ids?: string[] | null },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    throw new Error(await parseApiError(r));
  }
  // Parse a stream of `data: {json}\n\n` SSE frames manually. We avoid the
  // EventSource API because it doesn't support custom auth headers.
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    // Frames are separated by a blank line.
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!frame.startsWith("data:")) continue;
      const payload = frame.slice(5).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload) as ChatEvent);
      } catch {
        // Drop malformed frames silently — keeps a single bad chunk from killing the stream.
      }
    }
  }
}
