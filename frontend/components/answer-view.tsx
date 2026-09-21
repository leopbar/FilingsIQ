"use client";

import { Fragment, useState } from "react";
import { ExternalLink, FileText } from "lucide-react";

import type { AskResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Renders **bold** spans and turns [n] markers into citation chips. */
function renderInline(
  text: string,
  onCite: (n: number) => void,
  active: number | null,
  max: number,
) {
  return text.split(/(\*\*[^*]+\*\*|\[\d+\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    const cite = /^\[(\d+)\]$/.exec(part);
    if (cite) {
      const n = Number(cite[1]);
      if (n >= 1 && n <= max) {
        return (
          <button
            key={i}
            onClick={() => onCite(n)}
            aria-label={`Show source ${n}`}
            className={cn(
              "mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-px items-center justify-center rounded-md px-1 align-middle text-[0.65rem] font-semibold transition-colors",
              active === n
                ? "bg-primary text-primary-foreground"
                : "bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {n}
          </button>
        );
      }
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function AnswerView({ result }: { result: AskResponse }) {
  const [active, setActive] = useState<number | null>(null);
  const count = result.sources.length;
  const paragraphs = result.answer.split(/\n{2,}/).filter((p) => p.trim());

  return (
    <div className="space-y-4">
      <div className="space-y-3 text-[0.95rem] leading-7">
        {paragraphs.map((paragraph, i) => (
          <p key={i} className="whitespace-pre-wrap">
            {renderInline(paragraph, (n) => setActive((cur) => (cur === n ? null : n)), active, count)}
          </p>
        ))}
      </div>

      {count > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-medium text-muted-foreground">Sources</span>
            {result.sources.map((_, index) => {
              const citation = result.citations?.[index];
              const n = index + 1;
              return (
                <button
                  key={n}
                  onClick={() => setActive((cur) => (cur === n ? null : n))}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                    active === n
                      ? "border-primary bg-accent text-accent-foreground"
                      : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
                  )}
                >
                  <span className="font-semibold text-foreground">{n}</span>
                  <span className="max-w-40 truncate">
                    {citation ? `${citation.ticker || "Doc"} ${citation.fiscal_year}`.trim() : "Excerpt"}
                  </span>
                </button>
              );
            })}
          </div>

          {active !== null && result.sources[active - 1] !== undefined && (
            <div className="animate-fade-up rounded-xl border bg-muted/50 p-4">
              {(() => {
                const citation = result.citations?.[active - 1];
                return (
                  citation && (
                    <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span className="inline-flex items-center gap-1.5 font-medium">
                        <FileText className="size-3.5 text-primary" />
                        {citation.title}
                      </span>
                      {citation.filing_date && (
                        <span className="text-muted-foreground">Filed {citation.filing_date}</span>
                      )}
                      {citation.sec_url && (
                        <a
                          href={citation.sec_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-primary hover:underline"
                        >
                          Open on sec.gov <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                  )
                );
              })()}
              <p className="max-h-56 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                {result.sources[active - 1].trim()}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
