import type { Citation } from "./api";

/**
 * Render a list of pages as a tooltip-friendly suffix for a citation chip.
 * Single page → ", p3"; multiple pages → ", pp. 3–5".
 *
 * Lives here (not inline in MessageBubble.tsx) so it's importable from unit
 * tests without spinning up React.
 */
export function formatChipPages(pages: number[]): string {
  if (!pages.length) return "";
  if (pages.length === 1) return `, p${pages[0]}`;
  return `, pp. ${pages[0]}–${pages[pages.length - 1]}`;
}

/**
 * Turn raw LLM markdown into something safe for `<ReactMarkdown rehypePlugins={[rehypeRaw]}>`,
 * with our citation chip placeholders injected at `[n]` markers.
 *
 * Why this exists, and why the ordering matters:
 *
 *   1. `rehype-raw` renders ANY HTML in its input — so if the LLM emits
 *      `<script>` (intentionally or by quoting a malicious document), it
 *      would execute. To prevent that, we HTML-escape `<`, `>`, `&` FIRST.
 *   2. THEN we substitute `[n]` markers with `<cite data-n="n">n</cite>`
 *      tags. These are the only live HTML in the output — everything else
 *      was escaped to entities a step earlier.
 *   3. The frontend's `<ReactMarkdown components.cite>` override turns
 *      those `<cite>` tags into clickable citation buttons.
 *
 * Hallucinated citations (n not in the citations array) are silently
 * dropped — the model can't fake an authoritative-looking citation in the
 * UI even if it tries.
 */
const HTML_ESCAPES: Record<string, string> = {
  "<": "&lt;",
  ">": "&gt;",
  "&": "&amp;",
};

export function prepareContent(content: string, citations: Citation[]): string {
  let safe = content.replace(/[<>&]/g, (c) => HTML_ESCAPES[c] ?? c);

  if (citations.length) {
    const valid = new Set(citations.map((c) => c.n));
    safe = safe.replace(/\[(\d+)\]/g, (_match, n) => {
      const num = Number(n);
      if (!valid.has(num)) return "";
      return `<cite data-n="${num}">${num}</cite>`;
    });
  }

  return safe;
}
