import { X } from "lucide-react";
import type { Citation } from "@/lib/api";

interface Props {
  citation: Citation | null;
  onClose: () => void;
}

function formatPages(pages: number[]): string {
  if (pages.length === 0) return "";
  if (pages.length === 1) return `Page ${pages[0]}`;
  return `Pages ${pages[0]}–${pages[pages.length - 1]}`;
}

export default function CitationPanel({ citation, onClose }: Props) {
  if (!citation) return null;
  return (
    <div className="flex h-full w-80 flex-col border-l border-border bg-panel">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink2">Source [{citation.n}]</div>
          <div className="mt-0.5 truncate text-sm font-medium" title={citation.filename}>
            {citation.filename}
          </div>
          {citation.pages.length > 0 && (
            <div className="mt-0.5 text-xs text-ink2">{formatPages(citation.pages)}</div>
          )}
        </div>
        <button onClick={onClose} className="btn-ghost p-1">
          <X size={14} />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink2">
          {citation.snippet}
        </div>
      </div>
    </div>
  );
}
