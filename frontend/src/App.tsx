import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import type { Doc } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import AuthScreen from "./components/AuthScreen";
import Sidebar from "./components/Sidebar";
import ChatPane from "./components/ChatPane";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });
    const sub = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.data.subscription.unsubscribe();
  }, []);

  if (!authReady) return null;
  if (!session) return <AuthScreen />;
  return <Shell email={session.user.email ?? ""} />;
}

function Shell({ email }: { email: string }) {
  // Persisted so a refresh keeps you in the same conversation instead of
  // dropping back to the empty state. The chat is always in the DB + sidebar;
  // this just re-selects it. A stale/foreign id is handled in ChatPane's load
  // (it resets to null if the conversation can't be loaded).
  const [conversationId, setConversationId] = useLocalStorage<string | null>(
    "doc-chat:conversation-id",
    null,
  );
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [availableDocs, setAvailableDocs] = useState<Doc[]>([]);
  const [convRefresh, setConvRefresh] = useState(0);
  const [docsRefresh] = useState(0);

  // Persist sidebar collapsed state — small thing, but the kind of UX detail
  // that gets noticed when it's missing.
  const [collapsed, setCollapsed] = useLocalStorage<boolean>(
    "doc-chat:sidebar-collapsed",
    false,
  );

  // ⌘B / Ctrl+B toggles the sidebar (VS Code / Cursor / Linear convention).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCollapsed]);

  // Bump conversation list whenever a brand-new chat gets an id assigned
  // (so the just-created conversation appears in the sidebar immediately).
  useEffect(() => {
    if (conversationId) setConvRefresh((n) => n + 1);
  }, [conversationId]);

  return (
    <div className="flex h-full">
      <Sidebar
        email={email}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((c) => !c)}
        conversationId={conversationId}
        onSelectConversation={setConversationId}
        refreshConversations={convRefresh}
        onDocsChanged={setAvailableDocs}
        docsRefresh={docsRefresh}
      />

      <ChatPane
        conversationId={conversationId}
        setConversationId={setConversationId}
        availableDocs={availableDocs}
        selectedDocs={selectedDocs}
        onChangeSelectedDocs={setSelectedDocs}
      />
    </div>
  );
}
