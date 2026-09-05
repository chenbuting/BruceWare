import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ASSET_IMG_RE = /\/api\/v1\/kb\/assets\/(\d+)\/file/;

function assetIdFromUrl(url: string): number | null {
  const matched = url.trim().match(ASSET_IMG_RE);
  return matched ? Number(matched[1]) : null;
}

/** 提问回答：按 Markdown 显示表格、图片、列表，样式跟知识库一致。 */
export function KbAnswerContent({
  text,
  onOpenAsset,
}: {
  text: string;
  onOpenAsset?: (assetId: number) => void;
}) {
  const markdown = useMemo(() => (text || "").trim(), [text]);
  if (!markdown) return null;

  return (
    <div className="kb-answer-md space-y-2.5 text-[13px] leading-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h3 className="mt-3 text-[15px] font-semibold first:mt-0">{children}</h3>,
          h2: ({ children }) => <h3 className="mt-3 text-[15px] font-semibold first:mt-0">{children}</h3>,
          h3: ({ children }) => <h4 className="mt-2.5 text-[13px] font-semibold first:mt-0">{children}</h4>,
          h4: ({ children }) => <h4 className="mt-2 text-[13px] font-semibold first:mt-0">{children}</h4>,
          p: ({ node, children }) => {
            const hasBlock = node?.children?.some(
              (child) => child.type === "element" && (child.tagName === "img" || child.tagName === "figure"),
            );
            if (hasBlock) return <div className="leading-6">{children}</div>;
            return <p className="leading-6">{children}</p>;
          },
          ul: ({ children }) => <ul className="my-1 list-disc space-y-1 pl-5 marker:text-[var(--muted)]">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 list-decimal space-y-1 pl-5 marker:text-[var(--muted)]">{children}</ol>,
          li: ({ children }) => <li className="leading-6">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          hr: () => <hr className="my-3 border-[var(--line)]" />,
          blockquote: ({ children }) => (
            <blockquote className="rounded-r border-l-2 border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--muted)]">
              {children}
            </blockquote>
          ),
          code: ({ className, children }) => {
            if (className?.includes("language-")) {
              return <code className="block overflow-x-auto bg-[var(--code)] px-3 py-2 text-[12px] leading-6">{children}</code>;
            }
            return <code className="rounded bg-[var(--code)] px-1 py-0.5 text-[12px]">{children}</code>;
          },
          pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto rounded-md border border-[var(--line)]">
              <table className="min-w-full border-collapse text-left text-[13px]">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[var(--bg)] text-[var(--muted)]">{children}</thead>,
          th: ({ children }) => <th className="border-b border-[var(--line)] px-3 py-2 font-medium">{children}</th>,
          td: ({ children }) => <td className="border-b border-[var(--line)] px-3 py-2 align-top">{children}</td>,
          a: ({ href, children }) => {
            const url = (href || "").trim();
            if (/^https?:\/\//i.test(url) || url.startsWith("/api/")) {
              return (
                <a href={url} target="_blank" rel="noreferrer" className="underline hover:text-[var(--text)]">
                  {children}
                </a>
              );
            }
            return <span>{children}</span>;
          },
          img: ({ src, alt }) => {
            const url = (src || "").trim();
            const assetId = assetIdFromUrl(url);
            if (!url || (!assetId && !/^https?:\/\//i.test(url))) {
              return alt ? <span className="text-[12px] text-[var(--muted)]">[{alt}]</span> : null;
            }
            const image = (
              <img src={url} alt={alt || "图片"} className="max-h-64 w-auto rounded border border-[var(--line)] object-contain" />
            );
            if (assetId && onOpenAsset) {
              return (
                <button type="button" className="my-2 block max-w-full text-left" onClick={() => onOpenAsset(assetId)}>
                  {image}
                  {alt ? <span className="mt-1 block text-[12px] text-[var(--muted)]">{alt}</span> : null}
                </button>
              );
            }
            return (
              <span className="my-2 block">
                {image}
                {alt ? <span className="mt-1 block text-[12px] text-[var(--muted)]">{alt}</span> : null}
              </span>
            );
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

export function answerHasAsset(text: string, assetId: number): boolean {
  return text.includes(`/api/v1/kb/assets/${assetId}/file`);
}
