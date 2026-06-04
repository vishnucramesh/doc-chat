import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Sparkles } from "lucide-react";
import type { Citation } from "@/lib/api";
import { formatChipPages, prepareContent } from "@/lib/markdown";
import { cn } from "@/lib/utils";

interface Props {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  streaming?: boolean;
  onCitationClick?: (c: Citation) => void;
}

export default function MessageBubble({
  role,
  content,
  citations,
  streaming,
  onCitationClick,
}: Props) {
  const cites = citations ?? [];
  const prepared = useMemo(() => prepareContent(content, cites), [content, cites]);

  const prose = (
    <div
      className={cn(
        "prose prose-invert max-w-none text-[15px] leading-7",
        "prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5",
        "prose-headings:mt-4 prose-headings:mb-2",
        "prose-pre:bg-panel prose-pre:border prose-pre:border-border",
        "prose-code:text-ink prose-code:bg-panel2 prose-code:rounded prose-code:px-1 prose-code:py-0.5 prose-code:before:content-none prose-code:after:content-none",
        streaming && "cursor-blink",
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // Custom renderer for the <cite> sentinels we inject in prepareContent.
          // The 'data-n' attribute carries the citation number.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          cite: ({ children, ...props }: any) => {
            const n = Number(props["data-n"]);
            const c = cites.find((x) => x.n === n);
            if (!c) return <>{children}</>;
            return (
              <button
                type="button"
                className="citation-chip"
                onClick={() => onCitationClick?.(c)}
                title={`${c.filename}${formatChipPages(c.pages)}`}
              >
                {n}
              </button>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );

  // User message — a soft rounded bubble pinned to the right. Bubble background
  // is the elevated surface (panel2), not an accent tint, so the focus stays
  // on the assistant's reply, which is the actual content the user is reading.
  if (role === "user") {
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[80%] rounded-3xl bg-panel2 px-5 py-2.5 text-[15px] leading-7 text-ink">
          {prose}
        </div>
      </div>
    );
  }

  // Assistant message — deliberately bubble-less. ChatGPT does this and it's
  // the single biggest contributor to "this app reads like a chat product."
  // A tiny mark to the left signals where the assistant turn begins; the rest
  // is plain prose on the canvas.
  return (
    <div className="flex w-full gap-3">
      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
        <Sparkles size={13} />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">{prose}</div>
    </div>
  );
}
