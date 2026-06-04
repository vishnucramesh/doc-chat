import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, FileText, Globe } from "lucide-react";
import type { Doc } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  docs: Doc[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}

/**
 * A small chip-with-popover that controls which documents the chat queries.
 * Sits above the composer so it's visible without having to navigate to the
 * sidebar — the original layout hid this behind a sidebar toggle and people
 * (rightly) didn't discover it.
 *
 * Default state: no filter set = search ALL ready docs. The label switches
 * between "All docs" and "N of M docs" so users can see at a glance what
 * scope their next question will run against.
 */
export default function DocFilterPicker({ docs, selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Click-outside to close. A small but expected behavior for popovers; not
  // worth pulling in @radix-ui/popover for one menu.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const ready = docs.filter((d) => d.status === "ready");
  const selectedCount = selected.size;
  const filtering = selectedCount > 0;
  const label = !ready.length
    ? "No docs available"
    : filtering
      ? `${selectedCount} of ${ready.length} docs`
      : `All ${ready.length} docs`;

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }

  function clearAll() {
    onChange(new Set());
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={!ready.length}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] transition-colors",
          filtering
            ? "border-accent/40 bg-accent/10 text-accent"
            : "border-border text-ink2 hover:border-accent/40 hover:text-ink",
          !ready.length && "cursor-not-allowed opacity-50",
        )}
      >
        {filtering ? <FileText size={11} /> : <Globe size={11} />}
        <span>{label}</span>
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>

      {open && ready.length > 0 && (
        <div className="absolute bottom-full left-0 mb-1.5 w-72 rounded-lg border border-border bg-panel shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink2">
              Search scope
            </span>
            {filtering && (
              <button
                onClick={clearAll}
                className="text-[10px] text-accent hover:underline"
              >
                Use all docs
              </button>
            )}
          </div>
          <ul className="max-h-64 overflow-y-auto py-1">
            {ready.map((d) => {
              const checked = selected.has(d.id);
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => toggle(d.id)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-panel2"
                  >
                    <div
                      className={cn(
                        "flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border",
                        checked
                          ? "border-accent bg-accent text-black"
                          : "border-border",
                      )}
                    >
                      {checked && <Check size={10} strokeWidth={3} />}
                    </div>
                    <span className="min-w-0 flex-1 truncate" title={d.filename}>
                      {d.filename}
                    </span>
                    <span className="flex-shrink-0 text-[10px] text-ink2">
                      {d.chunk_count}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-border px-3 py-2 text-[10px] text-ink2/80">
            {filtering
              ? `Chat will only search the ${selectedCount} selected doc${selectedCount === 1 ? "" : "s"}.`
              : "Chat searches all ready docs by default."}
          </div>
        </div>
      )}
    </div>
  );
}
