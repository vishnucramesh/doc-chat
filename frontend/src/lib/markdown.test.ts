import { describe, expect, it } from "vitest";
import type { Citation } from "./api";
import { formatChipPages, prepareContent } from "./markdown";

// Tiny factory — only the fields prepareContent / formatChipPages actually
// touch are set; the rest are filler. Kept inline (not a shared fixture)
// because spreading literal objects reads cleaner in test assertions.
function cite(n: number, pages: number[] = [1]): Citation {
  return {
    n,
    chunk_id: `chunk-${n}`,
    document_id: `doc-${n}`,
    filename: `f${n}.pdf`,
    pages,
    snippet: "",
  };
}

describe("formatChipPages", () => {
  it("returns an empty string for no pages (text files)", () => {
    expect(formatChipPages([])).toBe("");
  });

  it("renders a single page as ', pN'", () => {
    expect(formatChipPages([3])).toBe(", p3");
  });

  it("renders multiple pages as a range from first to last (en-dash)", () => {
    expect(formatChipPages([3, 4, 5])).toBe(", pp. 3–5");
  });

  it("handles non-contiguous pages by still showing first–last range", () => {
    // We intentionally don't try to display "3, 5, 7" — too noisy in a
    // tooltip. First–last is the right summary even when the middle is
    // sparse.
    expect(formatChipPages([3, 7])).toBe(", pp. 3–7");
  });
});

describe("prepareContent — HTML escaping", () => {
  it("escapes raw < > & so LLM output can't inject live HTML through rehype-raw", () => {
    const out = prepareContent("<script>alert(1)</script>", []);
    expect(out).not.toContain("<script>");
    expect(out).toBe("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("escapes & before angle brackets so we don't double-escape", () => {
    // Order matters: if we escaped & last, "&amp;" would become "&amp;amp;".
    // The current implementation does a single pass with a character map,
    // which sidesteps that ordering trap entirely.
    expect(prepareContent("A & B < C", [])).toBe("A &amp; B &lt; C");
  });

  it("leaves plain text untouched", () => {
    expect(prepareContent("hello world", [])).toBe("hello world");
  });

  it("leaves markdown syntax alone (it gets parsed downstream)", () => {
    const md = "**bold** and *italic* and a [link](http://x)";
    expect(prepareContent(md, [])).toBe(md);
  });
});

describe("prepareContent — citation injection", () => {
  it("replaces [n] with a <cite> tag for valid citations", () => {
    const out = prepareContent("Foo [1] bar", [cite(1)]);
    expect(out).toBe('Foo <cite data-n="1">1</cite> bar');
  });

  it("silently drops hallucinated [n] markers (n not in citations)", () => {
    // The frontend's contract: the model can't fake authoritative-looking
    // citations. If it emits [5] and there's no citation #5, the marker
    // disappears rather than rendering as a broken chip.
    const out = prepareContent("Foo [5] bar", [cite(1)]);
    expect(out).toBe("Foo  bar");
    expect(out).not.toContain("[5]");
    expect(out).not.toContain("data-n");
  });

  it("handles multiple distinct citations in one message", () => {
    const out = prepareContent("First [1], second [2].", [cite(1), cite(2)]);
    expect(out).toBe(
      'First <cite data-n="1">1</cite>, second <cite data-n="2">2</cite>.',
    );
  });

  it("handles repeated references to the same citation", () => {
    const out = prepareContent("As shown [1], the [1] holds.", [cite(1)]);
    expect(out).toBe(
      'As shown <cite data-n="1">1</cite>, the <cite data-n="1">1</cite> holds.',
    );
  });

  it("does not match link markers like [text](url)", () => {
    // Citation regex is `\[(\d+)\]` — only digits inside the brackets, so
    // markdown links with arbitrary text never collide with it.
    const out = prepareContent("See [docs](https://example.com) for more.", []);
    expect(out).toBe("See [docs](https://example.com) for more.");
  });

  it("preserves surrounding markdown formatting around citations", () => {
    // This is the user-visible payoff: **bold [n]** now stays bold, where
    // the old two-pass renderer would have broken the `**` pairing.
    const out = prepareContent("**Header [1]**", [cite(1)]);
    expect(out).toBe('**Header <cite data-n="1">1</cite>**');
  });
});

describe("prepareContent — escape AND injection together", () => {
  it("escapes hostile HTML before any citation substitution", () => {
    // If the LLM tries to smuggle live HTML alongside a citation, the
    // escape pass should defuse the HTML while the cite injection still
    // runs over the (now-safe) text.
    const out = prepareContent("<img src=x onerror=alert(1)> [1]", [cite(1)]);
    expect(out).not.toContain("<img");
    expect(out).toContain('<cite data-n="1">1</cite>');
  });
});
