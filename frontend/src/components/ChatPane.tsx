import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles, Square } from "lucide-react";
import type { Citation, Doc, Message } from "@/lib/api";
import { getConversation, streamChat } from "@/lib/api";
import MessageBubble from "./MessageBubble";
import CitationPanel from "./CitationPanel";
import SourcesRow from "./SourcesRow";
import DocFilterPicker from "./DocFilterPicker";
import ErrorBanner from "./ErrorBanner";

interface Props {
  conversationId: string | null;
  setConversationId: (id: string | null) => void;
  availableDocs: Doc[];
  selectedDocs: Set<string>;
  onChangeSelectedDocs: (next: Set<string>) => void;
}

interface PendingAssistant {
  text: string;
  citations: Citation[];
}

const MAX_TEXTAREA_HEIGHT = 240; // px — about 10 lines before scroll kicks in
// How close to the bottom (in px) we still treat as "at the bottom" for the
// auto-scroll heuristic. Larger = more forgiving when the user is just barely
// scrolled up; smaller = more strict. 100px ≈ a couple of lines of context.
const NEAR_BOTTOM_PX = 100;

export default function ChatPane({
  conversationId,
  setConversationId,
  availableDocs,
  selectedDocs,
  onChangeSelectedDocs,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState<PendingAssistant | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // Set when the in-flight stream promotes a brand-new chat by calling
  // setConversationId from its own `meta` event. Distinguishes that
  // self-induced id change from the user actually switching conversations,
  // so the conversation-switch effect below doesn't abort the live stream.
  const selfSetConvRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // "Was the scroll viewport near the bottom right before this render?" —
  // captured BEFORE we re-render with new tokens so we don't get confused
  // by the new content pushing the scroller down ourselves.
  const wasNearBottomRef = useRef(true);

  // Auto-grow the textarea up to MAX_TEXTAREA_HEIGHT. Using useLayoutEffect
  // so the height change happens in the same paint as the value change —
  // avoids a one-frame jitter when typing fast.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [input]);

  // Conversation switch — abort any in-flight stream from the prior chat so
  // it doesn't keep firing setState into the wrong conversation's view.
  useEffect(() => {
    // The id change came from our own streaming response (new chat just got
    // its server id), not a user switch — keep the live stream and the
    // optimistic view we already have instead of aborting + reloading.
    if (selfSetConvRef.current) {
      selfSetConvRef.current = false;
      return;
    }
    abortRef.current?.abort();
    setOpenCitation(null);
    if (!conversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const detail = await getConversation(conversationId);
        if (!cancelled) setMessages(detail.messages);
      } catch {
        // A persisted id can go stale — conversation deleted, or a different
        // user signed in. Drop it and fall back to the empty state rather than
        // showing an error for a chat the user didn't actively open.
        if (!cancelled) {
          setMessages([]);
          setConversationId(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Track whether the user is near the bottom BEFORE each render — we sample
  // in a layout effect so the measurement reflects the previous layout, then
  // decide in a regular effect whether to follow content down.
  useLayoutEffect(() => {
    const sc = scrollerRef.current;
    if (!sc) return;
    wasNearBottomRef.current =
      sc.scrollHeight - sc.scrollTop - sc.clientHeight < NEAR_BOTTOM_PX;
  });

  useEffect(() => {
    // Only auto-scroll if the user hasn't scrolled up to read earlier
    // content. Otherwise we'd yank them back to the bottom on every token,
    // which is the single most annoying chat-UI antipattern.
    if (wasNearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ block: "end" });
    }
  }, [messages, pending]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setBusy(true);

    const userMsg: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setPending({ text: "", citations: [] });

    const ac = new AbortController();
    abortRef.current = ac;

    try {
      let convId = conversationId;
      let cites: Citation[] = [];
      let finalText = "";

      const docFilter = selectedDocs.size > 0 ? Array.from(selectedDocs) : null;

      await streamChat(
        { message: text, conversation_id: convId, document_ids: docFilter },
        (ev) => {
          if (ev.type === "meta") {
            cites = ev.citations;
            if (!convId) {
              convId = ev.conversation_id;
              selfSetConvRef.current = true;
              setConversationId(ev.conversation_id);
            }
            setPending({ text: "", citations: cites });
          } else if (ev.type === "token") {
            finalText += ev.text;
            setPending({ text: finalText, citations: cites });
          } else if (ev.type === "error") {
            setError(ev.message);
          }
        },
        ac.signal,
      );

      // Promote pending to a real message. If the user aborted, we keep
      // what we managed to stream so far — better than blank-erasing.
      setMessages((m) => [
        ...m,
        {
          id: `local-a-${Date.now()}`,
          role: "assistant",
          content: finalText,
          citations: cites,
          created_at: new Date().toISOString(),
        },
      ]);
      setPending(null);
    } catch (e) {
      // AbortError = user pressed Stop. Keep partial output as a real
      // message instead of throwing it away. Anything else is a real error.
      if (e instanceof DOMException && e.name === "AbortError") {
        setPending(null);
      } else {
        setError(e instanceof Error ? e.message : "chat failed");
        setPending(null);
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [busy, input, conversationId, selectedDocs, setConversationId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  const sendDisabled = !input.trim();

  return (
    <div className="flex h-full flex-1">
      <div className="flex h-full flex-1 flex-col">
        {/* No persistent header — ChatGPT keeps the chat surface clean.
            Conversation switching happens in the sidebar; if there's no
            conversation yet, the empty state below speaks for itself. */}

        <div ref={scrollerRef} className="flex-1 overflow-y-auto px-6 py-8">
          {messages.length === 0 && !pending ? (
            <EmptyState hasDocs={availableDocs.some((d) => d.status === "ready")} />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              {messages.map((m) => (
                <div key={m.id} className="flex flex-col">
                  <MessageBubble
                    role={m.role as "user" | "assistant"}
                    content={m.content}
                    citations={m.citations}
                    onCitationClick={setOpenCitation}
                  />
                  {m.role === "assistant" && (
                    <div className="ml-10 mt-1">
                      <SourcesRow citations={m.citations} onOpen={setOpenCitation} />
                    </div>
                  )}
                </div>
              ))}
              {pending && (
                <div className="flex flex-col">
                  <MessageBubble
                    role="assistant"
                    content={pending.text || "…"}
                    citations={pending.citations}
                    streaming
                    onCitationClick={setOpenCitation}
                  />
                  {pending.citations.length > 0 && (
                    <div className="ml-10 mt-1">
                      <SourcesRow citations={pending.citations} onOpen={setOpenCitation} />
                    </div>
                  )}
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <footer className="flex-shrink-0 px-6 pb-6 pt-2">
          {error && (
            <ErrorBanner
              message={error}
              onDismiss={() => setError(null)}
              className="mx-auto mb-2 max-w-3xl"
            />
          )}
          <div className="mx-auto max-w-3xl">
            <div className="composer-pill">
              <textarea
                ref={textareaRef}
                className="composer-textarea max-h-[240px] min-h-[28px]"
                rows={1}
                placeholder="Ask anything about your documents…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                disabled={busy}
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <DocFilterPicker
                  docs={availableDocs}
                  selected={selectedDocs}
                  onChange={onChangeSelectedDocs}
                />
                {busy ? (
                  <button
                    type="button"
                    className="send-btn"
                    onClick={stop}
                    title="Stop generating"
                    aria-label="Stop generating"
                  >
                    <Square size={12} strokeWidth={2.5} fill="currentColor" />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="send-btn"
                    onClick={() => void send()}
                    disabled={sendDisabled}
                    title="Send (Enter)"
                    aria-label="Send"
                  >
                    <ArrowUp size={14} strokeWidth={2.5} />
                  </button>
                )}
              </div>
            </div>
            <p className="mt-2 text-center text-[10px] text-ink2/60">
              doc-chat only answers from your uploaded files · Enter to send · Shift+Enter for newline · ⌘B to toggle sidebar
            </p>
          </div>
        </footer>
      </div>

      <CitationPanel citation={openCitation} onClose={() => setOpenCitation(null)} />
    </div>
  );
}

function EmptyState({ hasDocs }: { hasDocs: boolean }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/10 text-accent">
        <Sparkles size={26} />
      </div>
      <h1 className="text-3xl font-semibold tracking-tight text-ink">
        {hasDocs ? "Ask anything about your documents" : "Add a document to get started"}
      </h1>
      <p className="mt-3 max-w-md text-sm text-ink2">
        {hasDocs
          ? "Answers cite the exact page they came from. Click any source pill to see the snippet."
          : "Drop PDFs or text files in the sidebar. Once they finish processing, you can chat with them here."}
      </p>
    </div>
  );
}

