import { AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  message: string;
  onDismiss?: () => void;
  className?: string;
  /** Compact variant — used inside narrow sidebars where the full padding is too much. */
  compact?: boolean;
}

/**
 * Inline error alert. Used in place of the tiny one-line red spans that
 * preceded it — those were easy to miss and impossible to dismiss. This
 * component is small but real (icon, message, close button) and stylable
 * in two sizes.
 *
 * Deliberately not a toast: errors here are tied to a specific UI region
 * (the upload zone, the chat composer, the auth form) and should sit next
 * to the failed action, not float at the top of the viewport.
 */
export default function ErrorBanner({ message, onDismiss, className, compact }: Props) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 text-danger",
        compact ? "px-2 py-1.5 text-[11px]" : "px-3 py-2 text-xs",
        className,
      )}
    >
      <AlertTriangle
        size={compact ? 11 : 13}
        className="mt-0.5 flex-shrink-0"
        strokeWidth={2.25}
      />
      <span className="min-w-0 flex-1 leading-snug">{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="flex-shrink-0 rounded p-0.5 text-danger/70 hover:bg-danger/10 hover:text-danger"
        >
          <X size={compact ? 11 : 13} />
        </button>
      )}
    </div>
  );
}
