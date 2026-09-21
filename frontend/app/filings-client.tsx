"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowUp,
  FileUp,
  Globe,
  Loader2,
  Menu,
  Plus,
  Scale,
  Sparkles,
  X,
} from "lucide-react";

import { AnswerView } from "@/components/answer-view";
import { SecImportDialog } from "@/components/sec-import-dialog";
import { ThemeToggle } from "@/components/theme-toggle";
import { TickerAvatar } from "@/components/ticker-avatar";
import { ClassifierDialog, UploadDialog } from "@/components/tool-dialogs";
import { Button } from "@/components/ui/button";
import { api, UPLOAD_SCOPE, type AskResponse, type Company, type UploadResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

export type { Company };

interface Turn {
  id: number;
  question: string;
  scope: string;
  status: "loading" | "done" | "error";
  result?: AskResponse;
  error?: string;
}

interface FilingsClientProps {
  initialCompanies: Company[];
  initialImportEnabled: boolean;
  initialCompaniesError: string | null;
}

const SUGGESTIONS = [
  "What are the main risk factors?",
  "How did revenue change year over year?",
  "Who are the main competitors and how does the company describe competition?",
  "Summarize the business in plain language.",
];

const defaultTicker = (companies: Company[]) =>
  companies.find((company) => company.ticker === "AAPL")?.ticker ?? companies[0]?.ticker ?? "";

export default function FilingsClient({
  initialCompanies,
  initialImportEnabled,
  initialCompaniesError,
}: FilingsClientProps) {
  const [companies, setCompanies] = useState<Company[]>(initialCompanies);
  const [companiesError, setCompaniesError] = useState<string | null>(initialCompaniesError);
  const [importEnabled, setImportEnabled] = useState(initialImportEnabled);
  const [ticker, setTicker] = useState(defaultTicker(initialCompanies));
  const [year, setYear] = useState("all");
  const [upload, setUpload] = useState<UploadResponse | null>(null);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const nextId = useRef(1);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  const [navOpen, setNavOpen] = useState(false);
  const [secOpen, setSecOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [classifierOpen, setClassifierOpen] = useState(false);

  const isUpload = ticker === UPLOAD_SCOPE;
  const selectedCompany = useMemo(
    () => companies.find((company) => company.ticker === ticker),
    [companies, ticker],
  );
  const busy = turns.some((turn) => turn.status === "loading");
  const scopeLabel = isUpload
    ? "Uploaded document"
    : selectedCompany
      ? `${selectedCompany.ticker}${year !== "all" ? ` · ${year}` : ""}`
      : "";

  const loadCompanies = useCallback(async (selectTicker?: string) => {
    try {
      const payload = await api.companies();
      setCompanies(payload.companies);
      setImportEnabled(payload.import_enabled);
      setCompaniesError(null);
      setTicker((current) => {
        if (selectTicker) return selectTicker;
        if (current === UPLOAD_SCOPE || payload.companies.some((c) => c.ticker === current)) {
          return current;
        }
        return defaultTicker(payload.companies);
      });
      if (selectTicker) setYear("all");
    } catch (err) {
      setCompaniesError(err instanceof Error ? err.message : "Could not load companies");
    }
  }, []);

  // Keep the newest answer in view
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(
    async (text?: string) => {
      const q = (text ?? question).trim();
      if (!q || busy || !ticker) return;
      const id = nextId.current++;
      setQuestion("");
      setTurns((current) => [...current, { id, question: q, scope: scopeLabel, status: "loading" }]);
      try {
        const result = await api.ask(
          q,
          isUpload ? null : ticker,
          isUpload ? "upload" : year === "all" ? null : year,
        );
        setTurns((current) =>
          current.map((turn) => (turn.id === id ? { ...turn, status: "done", result } : turn)),
        );
      } catch (err) {
        const error = err instanceof Error ? err.message : "Unknown error";
        setTurns((current) =>
          current.map((turn) => (turn.id === id ? { ...turn, status: "error", error } : turn)),
        );
      }
    },
    [question, busy, ticker, scopeLabel, isUpload, year],
  );

  const selectScope = (next: string) => {
    setTicker(next);
    setYear("all");
    setNavOpen(false);
    composer.current?.focus();
  };

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-5">
        <span className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <Sparkles className="size-[1.1rem]" />
        </span>
        <div className="leading-tight">
          <p className="text-[0.95rem] font-semibold tracking-tight">FilingsIQ</p>
          <p className="text-xs text-muted-foreground">Chat with SEC filings</p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-label="Close menu"
        >
          <X />
        </Button>
      </div>

      <div className="px-3 pb-3">
        <Button
          className="h-10 w-full justify-start gap-2 rounded-xl"
          onClick={() => {
            setSecOpen(true);
            setNavOpen(false);
          }}
          disabled={!importEnabled}
          title={importEnabled ? undefined : "Company import is disabled on this deployment"}
        >
          <Plus /> Add company from SEC
        </Button>
      </div>

      <p className="px-4 pb-1.5 text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
        Companies
      </p>
      <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2" aria-label="Companies">
        {companies.map((company) => (
          <button
            key={company.ticker}
            onClick={() => selectScope(company.ticker)}
            aria-current={ticker === company.ticker}
            className={cn(
              "flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              ticker === company.ticker ? "bg-accent text-accent-foreground" : "hover:bg-muted",
            )}
          >
            <TickerAvatar ticker={company.ticker} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{company.company_name}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {company.ticker} · {company.fiscal_years.length}{" "}
                {company.fiscal_years.length === 1 ? "year" : "years"}
              </span>
            </span>
          </button>
        ))}
        {upload && (
          <button
            onClick={() => selectScope(UPLOAD_SCOPE)}
            aria-current={isUpload}
            className={cn(
              "flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              isUpload ? "bg-accent text-accent-foreground" : "hover:bg-muted",
            )}
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary">
              <FileUp className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{upload.filename}</span>
              <span className="block text-xs text-muted-foreground">Uploaded document</span>
            </span>
          </button>
        )}
        {companies.length === 0 && !upload && (
          <p className="px-2 py-4 text-sm text-muted-foreground">
            {companiesError ? `Couldn’t load companies: ${companiesError}` : "No companies indexed yet."}
          </p>
        )}
      </nav>

      <div className="space-y-0.5 border-t p-2">
        <button
          onClick={() => {
            setUploadOpen(true);
            setNavOpen(false);
          }}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <FileUp className="size-4" /> Upload a PDF
        </button>
        <button
          onClick={() => {
            setClassifierOpen(true);
            setNavOpen(false);
          }}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Scale className="size-4" /> Clause classifier
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden w-72 shrink-0 border-r bg-sidebar lg:block">{sidebar}</aside>

      {/* Mobile drawer */}
      <div className={cn("fixed inset-0 z-40 lg:hidden", navOpen ? "" : "pointer-events-none")}>
        <div
          onClick={() => setNavOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity",
            navOpen ? "opacity-100" : "opacity-0",
          )}
        />
        <aside
          inert={!navOpen}
          className={cn(
            "absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r bg-sidebar shadow-2xl transition-transform duration-200",
            navOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          {sidebar}
        </aside>
      </div>

      <main className="bg-aurora relative flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b bg-background/70 px-4 py-2.5 backdrop-blur-md">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setNavOpen(true)}
            aria-label="Open menu"
          >
            <Menu />
          </Button>
          <div className="min-w-0 flex-1">
            {isUpload ? (
              <p className="truncate text-sm font-semibold">{upload?.filename ?? "Uploaded document"}</p>
            ) : selectedCompany ? (
              <>
                <p className="truncate text-sm font-semibold">{selectedCompany.company_name}</p>
                <div className="mt-1 flex gap-1 overflow-x-auto pb-0.5" role="group" aria-label="Fiscal year">
                  {["all", ...selectedCompany.fiscal_years].map((fy) => (
                    <button
                      key={fy}
                      onClick={() => setYear(fy)}
                      aria-pressed={year === fy}
                      className={cn(
                        "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
                        year === fy
                          ? "bg-primary text-primary-foreground"
                          : "bg-secondary text-secondary-foreground hover:bg-accent",
                      )}
                    >
                      {fy === "all" ? "All years" : fy}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Select or add a company to begin</p>
            )}
          </div>
          <ThemeToggle />
        </header>

        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {turns.length === 0 ? (
              <div className="animate-fade-up flex flex-col items-center pt-10 text-center sm:pt-20">
                <span className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/25">
                  <Sparkles className="size-7" />
                </span>
                <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                  {selectedCompany || isUpload
                    ? `Ask anything about ${isUpload ? "your document" : selectedCompany?.company_name}`
                    : "Ask anything about SEC filings"}
                </h1>
                <p className="mt-2 max-w-md text-sm text-muted-foreground">
                  Answers are grounded in the filing text and cite the exact passages they come from.
                </p>
                {ticker ? (
                  <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => void ask(suggestion)}
                        className="rounded-xl border bg-card px-4 py-3 text-left text-sm shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                ) : (
                  importEnabled && (
                    <Button className="mt-8" onClick={() => setSecOpen(true)}>
                      <Globe /> Find a company on SEC EDGAR
                    </Button>
                  )
                )}
                {companiesError && (
                  <p className="mt-6 flex items-center gap-2 text-sm text-destructive">
                    <AlertCircle className="size-4" /> {companiesError}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-8">
                {turns.map((turn) => (
                  <section key={turn.id} className="animate-fade-up space-y-4">
                    <div className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
                        {turn.question}
                        {turn.scope && (
                          <span className="mt-1 block text-[0.7rem] opacity-70">{turn.scope}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-3">
                      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                        <Sparkles className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border bg-card px-5 py-4 shadow-sm">
                        {turn.status === "loading" && (
                          <div className="space-y-2.5" aria-label="Thinking">
                            <div className="skeleton h-3.5 w-11/12 rounded" />
                            <div className="skeleton h-3.5 w-full rounded" />
                            <div className="skeleton h-3.5 w-2/3 rounded" />
                          </div>
                        )}
                        {turn.status === "error" && (
                          <p className="flex items-start gap-2 text-sm text-destructive">
                            <AlertCircle className="mt-0.5 size-4 shrink-0" />
                            {turn.error}
                          </p>
                        )}
                        {turn.status === "done" && turn.result && <AnswerView result={turn.result} />}
                      </div>
                    </div>
                  </section>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="border-t bg-background/70 px-4 pb-4 pt-3 backdrop-blur-md">
          <div className="mx-auto w-full max-w-3xl">
            <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm transition-shadow focus-within:border-ring focus-within:shadow-md focus-within:ring-4 focus-within:ring-ring/15">
              <textarea
                ref={composer}
                aria-label="Your question"
                rows={1}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void ask();
                  }
                }}
                disabled={!ticker}
                placeholder={
                  ticker
                    ? `Ask about ${isUpload ? "the uploaded document" : selectedCompany?.company_name}…`
                    : "Select or add a company first"
                }
                className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60 [field-sizing:content]"
              />
              <Button
                size="icon-lg"
                className="rounded-xl"
                onClick={() => void ask()}
                disabled={busy || !question.trim() || !ticker}
                aria-label="Send question"
              >
                {busy ? <Loader2 className="animate-spin" /> : <ArrowUp />}
              </Button>
            </div>
            <p className="mt-2 text-center text-[0.7rem] text-muted-foreground">
              Answers come from SEC filings and may contain mistakes — verify against the cited source.
            </p>
          </div>
        </div>
      </main>

      <SecImportDialog
        open={secOpen}
        onOpenChange={setSecOpen}
        onImported={(imported) => void loadCompanies(imported)}
      />
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(result) => {
          setUpload(result);
          setTicker(UPLOAD_SCOPE);
          setYear("all");
        }}
      />
      <ClassifierDialog open={classifierOpen} onOpenChange={setClassifierOpen} />
    </div>
  );
}
