import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronsLeft,
  FileText,
  LogOut,
  Loader2,
  MessageSquarePlus,
  PanelLeftOpen,
  Trash2,
  Upload,
} from "lucide-react";
import type { Conversation, Doc } from "@/lib/api";
import {
  deleteConversation,
  deleteDocument,
  listConversations,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { cn, formatBytes } from "@/lib/utils";
import ErrorBanner from "./ErrorBanner";
import ConfirmDialog from "./ConfirmDialog";

interface ConfirmState {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
}

interface Props {
  email: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  conversationId: string | null;
  onSelectConversation: (id: string | null) => void;
  refreshConversations: number;
  onDocsChanged: (docs: Doc[]) => void;
  docsRefresh: number;
}

const DOC_POLL_MS = 2000;

export default function Sidebar({
  email,
  collapsed,
  onToggleCollapsed,
  conversationId,
  onSelectConversation,
  refreshConversations,
  onDocsChanged,
  docsRefresh,
}: Props) {
  // In-app confirmation modal — replaces window.confirm() for destructive
  // actions. Holds the pending action; null when the dialog is closed.
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  // ─── Conversations ──────────────────────────────────────────────────────
  const [conversations, setConversations] = useState<Conversation[]>([]);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await listConversations();
        if (!cancelled) setConversations(next);
      } catch {
        // Soft-fail: keep the previous list rather than flashing empty state.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshConversations]);

  const handleDeleteConversation = useCallback(
    (id: string) => {
      setConfirmState({
        title: "Delete conversation?",
        message: "This conversation and its messages will be permanently removed.",
        confirmLabel: "Delete",
        onConfirm: async () => {
          await deleteConversation(id);
          setConversations((cs) => cs.filter((c) => c.id !== id));
          if (conversationId === id) onSelectConversation(null);
        },
      });
    },
    [conversationId, onSelectConversation],
  );

  // ─── Documents ──────────────────────────────────────────────────────────
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploading, setUploading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshDocs = useCallback(async () => {
    try {
      const next = await listDocuments();
      setDocs(next);
      onDocsChanged(next);
    } catch (e) {
      setDocError(e instanceof Error ? e.message : "failed to list documents");
    }
  }, [onDocsChanged]);

  useEffect(() => {
    void refreshDocs();
  }, [refreshDocs, docsRefresh]);

  // Poll while any document is still ingesting. Stops as soon as none are.
  const anyProcessing = useMemo(
    () => docs.some((d) => d.status === "pending" || d.status === "processing"),
    [docs],
  );
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(refreshDocs, DOC_POLL_MS);
    return () => clearInterval(t);
  }, [anyProcessing, refreshDocs]);

  const handleFiles = useCallback(
    async (files: FileList | File[] | null) => {
      if (!files || files.length === 0) return;
      setUploading(true);
      setDocError(null);
      try {
        for (const f of Array.from(files)) {
          await uploadDocument(f);
        }
        await refreshDocs();
      } catch (e) {
        setDocError(e instanceof Error ? e.message : "upload failed");
      } finally {
        setUploading(false);
      }
    },
    [refreshDocs],
  );

  const handleDeleteDoc = useCallback(
    (id: string) => {
      setConfirmState({
        title: "Delete document?",
        message: "The document and all its chunks will be permanently removed.",
        confirmLabel: "Delete",
        onConfirm: async () => {
          try {
            await deleteDocument(id);
            setDocs((d) => d.filter((x) => x.id !== id));
            onDocsChanged(docs.filter((x) => x.id !== id));
          } catch (e) {
            setDocError(e instanceof Error ? e.message : "delete failed");
          }
        },
      });
    },
    [docs, onDocsChanged],
  );

  // ─── Render ─────────────────────────────────────────────────────────────
  // Width animates between 0 and 280px; when collapsed we slide off-screen
  // rather than rendering a tiny icon rail — keeps the chat pane full-width
  // and matches the "back to a clean canvas" feeling of Claude/ChatGPT.
  return (
    <>
      {collapsed && (
        <button
          onClick={onToggleCollapsed}
          className="btn-ghost fixed left-3 top-3 z-30 h-8 w-8 rounded-md border border-border bg-panel/80 p-0 shadow-sm backdrop-blur"
          title="Open sidebar (⌘B)"
        >
          <PanelLeftOpen size={16} />
        </button>
      )}

      <aside
        className={cn(
          "flex h-full flex-col overflow-hidden border-r border-border bg-panel transition-[width] duration-200 ease-out",
          collapsed ? "w-0 border-r-0" : "w-72",
        )}
      >
        {/* Header */}
        <div className="flex h-12 flex-shrink-0 items-center justify-between border-b border-border px-3">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15 text-accent">
              <FileText size={13} />
            </div>
            <span className="text-sm font-semibold">doc-chat</span>
          </div>
          <button
            onClick={onToggleCollapsed}
            className="btn-ghost p-1"
            title="Collapse sidebar (⌘B)"
          >
            <ChevronsLeft size={14} />
          </button>
        </div>

        {/* New chat */}
        <div className="border-b border-border px-2 py-2">
          <button
            onClick={() => onSelectConversation(null)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium text-ink hover:bg-panel2"
          >
            <MessageSquarePlus size={13} />
            New chat
          </button>
        </div>

        {/* Sections — flex-1 with internal scroll so the user card stays pinned */}
        <div className="flex flex-1 flex-col overflow-y-auto">
          <Section title="Conversations" count={conversations.length}>
            {conversations.length === 0 ? (
              <EmptyHint text="No conversations yet" />
            ) : (
              <ul className="space-y-0.5">
                {conversations.map((c) => (
                  <ConversationItem
                    key={c.id}
                    conv={c}
                    active={conversationId === c.id}
                    onSelect={() => onSelectConversation(c.id)}
                    onDelete={() => handleDeleteConversation(c.id)}
                  />
                ))}
              </ul>
            )}
          </Section>

          <Section title="Files" count={docs.length}>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                void handleFiles(e.dataTransfer.files);
              }}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "mb-2 flex cursor-pointer items-center justify-center gap-1.5 rounded-md border border-dashed py-2 text-[11px] transition-colors",
                dragOver
                  ? "border-accent bg-accent/5 text-ink"
                  : "border-border text-ink2 hover:border-accent/50 hover:text-ink",
              )}
            >
              {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
              <span>{uploading ? "Uploading…" : "Drop or click to upload"}</span>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                multiple
                accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                onChange={(e) => void handleFiles(e.target.files)}
              />
            </div>
            {docError && (
              <ErrorBanner
                compact
                message={docError}
                onDismiss={() => setDocError(null)}
                className="mb-2"
              />
            )}

            {docs.length === 0 ? (
              <EmptyHint text="No files yet" />
            ) : (
              <ul className="space-y-0.5">
                {docs.map((d) => (
                  <DocItem key={d.id} doc={d} onDelete={() => handleDeleteDoc(d.id)} />
                ))}
              </ul>
            )}
          </Section>
        </div>

        {/* User card pinned to bottom */}
        <div className="flex flex-shrink-0 items-center gap-2 border-t border-border px-3 py-2.5">
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent">
            {email.slice(0, 2).toUpperCase()}
          </div>
          <span className="min-w-0 flex-1 truncate text-xs text-ink2" title={email}>
            {email}
          </span>
          <button
            onClick={() => void supabase.auth.signOut()}
            className="btn-ghost p-1"
            title="Sign out"
          >
            <LogOut size={12} />
          </button>
        </div>
      </aside>

      <ConfirmDialog
        open={confirmState !== null}
        title={confirmState?.title ?? ""}
        message={confirmState?.message}
        confirmLabel={confirmState?.confirmLabel}
        destructive
        onCancel={() => setConfirmState(null)}
        onConfirm={() => {
          void confirmState?.onConfirm();
          setConfirmState(null);
        }}
      />
    </>
  );
}

// ─── Section ──────────────────────────────────────────────────────────────
function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-border/50 px-2 py-3 last:border-b-0">
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-ink2">
          {title}
        </h3>
        <span className="text-[10px] text-ink2/70">{count}</span>
      </div>
      {children}
    </section>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <p className="px-2 py-2 text-[11px] text-ink2/60">{text}</p>;
}

// ─── Conversation item ────────────────────────────────────────────────────
function ConversationItem({
  conv,
  active,
  onSelect,
  onDelete,
}: {
  conv: Conversation;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <li>
      <div
        onClick={onSelect}
        className={cn(
          "group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs",
          active
            ? "bg-panel2 text-ink"
            : "text-ink2 hover:bg-panel2 hover:text-ink",
        )}
      >
        <span className="flex-1 truncate" title={conv.title ?? "Untitled"}>
          {conv.title || "Untitled"}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            void onDelete();
          }}
          className="opacity-0 hover:text-danger group-hover:opacity-100"
        >
          <Trash2 size={11} />
        </button>
      </div>
    </li>
  );
}

// ─── Doc item ─────────────────────────────────────────────────────────────
function DocItem({ doc, onDelete }: { doc: Doc; onDelete: () => void }) {
  return (
    <li className="group flex items-start gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-panel2">
      <FileText size={12} className="mt-0.5 flex-shrink-0 text-ink2" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-ink" title={doc.filename}>
          {doc.filename}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink2">
          <DocStatus status={doc.status} />
          {doc.status === "ready" && <span>{doc.chunk_count} chunks</span>}
          <span>{formatBytes(doc.size_bytes)}</span>
        </div>
        {doc.status === "failed" && doc.error && (
          <div className="mt-1 text-[10px] text-danger">{doc.error}</div>
        )}
      </div>
      <button
        onClick={onDelete}
        className="opacity-0 hover:text-danger group-hover:opacity-100"
        title="Delete"
      >
        <Trash2 size={11} />
      </button>
    </li>
  );
}

function DocStatus({ status }: { status: Doc["status"] }) {
  switch (status) {
    case "ready":
      return (
        <span className="inline-flex items-center gap-1 text-accent">
          <CheckCircle2 size={9} /> ready
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1 text-danger">
          <AlertTriangle size={9} /> failed
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1">
          <Loader2 size={9} className="animate-spin" /> {status}
        </span>
      );
  }
}
