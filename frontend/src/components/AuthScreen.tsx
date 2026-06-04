import { useState } from "react";
import { CheckCircle2, FileText, Loader2, Mail } from "lucide-react";
import { supabase } from "@/lib/supabase";
import ErrorBanner from "./ErrorBanner";

type Mode = "sign-in" | "sign-up";

export default function AuthScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<Mode>("sign-in");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When set, we switch to the "check your email" view. Holds the address we
  // sent verification to so the message can name it specifically — much more
  // reassuring than "we sent it to your email" when you have multiple inboxes.
  const [pendingVerifyEmail, setPendingVerifyEmail] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "sign-in") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          // Supabase returns "Email not confirmed" verbatim when a user tries
          // to sign in pre-verification. Route to the verification view instead
          // of showing it as a generic error — the recovery path is "go check
          // your email" not "try again".
          if (/email\s+not\s+confirmed/i.test(error.message)) {
            setPendingVerifyEmail(email);
            return;
          }
          throw error;
        }
      } else {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setPendingVerifyEmail(email);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  if (pendingVerifyEmail) {
    return (
      <VerifyEmailView
        email={pendingVerifyEmail}
        onBack={() => {
          setPendingVerifyEmail(null);
          setError(null);
          setMode("sign-in");
        }}
      />
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="card w-full max-w-sm p-6">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
            <FileText size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold">doc-chat</h1>
            <p className="text-xs text-ink2">Chat with your documents</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink2">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink2">Password</span>
            <input
              type="password"
              required
              autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
              minLength={6}
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy && <Loader2 size={14} className="animate-spin" />}
            {mode === "sign-in" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "sign-in" ? "sign-up" : "sign-in");
            setError(null);
          }}
          className="mt-4 w-full text-xs text-ink2 hover:text-ink"
        >
          {mode === "sign-in" ? "Need an account? Sign up" : "Have an account? Sign in"}
        </button>
      </div>
    </div>
  );
}

function VerifyEmailView({ email, onBack }: { email: string; onBack: () => void }) {
  const [resendBusy, setResendBusy] = useState(false);
  const [resentAt, setResentAt] = useState<number | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);

  async function resend() {
    setResendBusy(true);
    setResendError(null);
    try {
      const { error } = await supabase.auth.resend({ type: "signup", email });
      if (error) throw error;
      setResentAt(Date.now());
    } catch (err) {
      setResendError(err instanceof Error ? err.message : "Couldn't resend");
    } finally {
      setResendBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="card w-full max-w-md p-7 text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
          <Mail size={22} />
        </div>
        <h1 className="text-xl font-semibold text-ink">Check your email</h1>
        <p className="mt-2 text-sm text-ink2">
          We sent a verification link to{" "}
          <span className="font-medium text-ink">{email}</span>. Click it to activate
          your account, then come back here to sign in.
        </p>
        <p className="mt-3 text-xs text-ink2/70">
          The link is valid for one hour. Check your spam folder if you don't see it.
        </p>

        {resendError && (
          <ErrorBanner
            message={resendError}
            onDismiss={() => setResendError(null)}
            className="mt-4 text-left"
          />
        )}
        {resentAt && !resendError && (
          <div className="mt-4 flex items-center justify-center gap-1.5 text-xs text-accent">
            <CheckCircle2 size={12} />
            <span>Verification email resent.</span>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={resend}
            disabled={resendBusy}
            className="btn-ghost w-full justify-center border border-border"
          >
            {resendBusy ? (
              <>
                <Loader2 size={13} className="animate-spin" /> Resending…
              </>
            ) : (
              "Resend verification email"
            )}
          </button>
          <button
            type="button"
            onClick={onBack}
            className="w-full text-xs text-ink2 hover:text-ink"
          >
            Back to sign in
          </button>
        </div>
      </div>
    </div>
  );
}
