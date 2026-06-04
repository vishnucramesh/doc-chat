import { useMemo } from "react";
import { FileText } from "lucide-react";
import type { Citation } from "@/lib/api";

interface Props {
  citations: Citation[] | null | undefined;
  onOpen: (c: Citation) => void;
}

/**
 * "Sources" row rendered under each assistant message. Before this, citations
 * were only reachable via the inline [n] chips, and you couldn't see which
 * filenames an answer was grounded in without clicking each one. This row
 * surfaces that at a glance, and groups consecutive citations from the same
 * file so the chip strip stays short even when the model cites 8 chunks.
 *
 * Grouping is by (document_id) — pages within the same document are shown
 * as a comma list inside the chip. We considered (document_id, page) but
 * for typical answers it produced too many near-identical chips.
 */
export default function SourcesRow({ citations, onOpen }: Props) {
  const groups = useMemo(() => groupByDocument(citations ?? []), [citations]);
  if (!groups.length) return null;

  return (
    <div className="mt-3 border-t border-border/60 pt-2">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink2">
        Sources
      </div>
      <div className="flex flex-wrap gap-1.5">
        {groups.map((g) => (
          <SourceChip key={g.document_id} group={g} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

interface SourceGroup {
  document_id: string;
  filename: string;
  pages: number[];      // sorted, unique
  citations: Citation[]; // sorted by page then [n]
}

function groupByDocument(citations: Citation[]): SourceGroup[] {
  const map = new Map<string, SourceGroup>();
  for (const c of citations) {
    let g = map.get(c.document_id);
    if (!g) {
      g = { document_id: c.document_id, filename: c.filename, pages: [], citations: [] };
      map.set(c.document_id, g);
    }
    g.citations.push(c);
    // Each citation now carries a list of pages (its window's full span),
    // so flatten everything into a deduped sorted list per document.
    for (const p of c.pages) {
      if (!g.pages.includes(p)) g.pages.push(p);
    }
  }
  for (const g of map.values()) {
    g.pages.sort((a, b) => a - b);
    g.citations.sort(
      (a, b) => (a.pages[0] ?? 0) - (b.pages[0] ?? 0) || a.n - b.n,
    );
  }
  return Array.from(map.values());
}

function SourceChip({
  group,
  onOpen,
}: {
  group: SourceGroup;
  onOpen: (c: Citation) => void;
}) {
  const pageLabel = group.pages.length
    ? group.pages.length === 1
      ? `p. ${group.pages[0]}`
      : `pp. ${group.pages.slice(0, 3).join(", ")}${group.pages.length > 3 ? "…" : ""}`
    : null;

  // Open the first citation in the group when the chip is clicked. The user
  // can then scroll the panel for adjacent chunks — beats popping a nested
  // dropdown for what is usually 1–2 chunks per doc.
  return (
    <button
      type="button"
      onClick={() => onOpen(group.citations[0])}
      className="group inline-flex max-w-[260px] items-center gap-1.5 rounded-md border border-border bg-panel2/60 px-2 py-1 text-[11px] transition-colors hover:border-accent/40 hover:bg-panel2"
      title={`${group.filename}${pageLabel ? ` — ${pageLabel}` : ""}`}
    >
      <FileText size={10} className="flex-shrink-0 text-ink2 group-hover:text-accent" />
      <span className="truncate text-ink">{group.filename}</span>
      {pageLabel && <span className="flex-shrink-0 text-ink2">· {pageLabel}</span>}
      {group.citations.length > 1 && (
        <span className="flex-shrink-0 rounded-sm bg-accent/15 px-1 text-[9px] font-semibold text-accent">
          {group.citations.length}
        </span>
      )}
    </button>
  );
}
