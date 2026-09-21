"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TickerAvatar } from "@/components/ticker-avatar";
import {
  api,
  MAX_IMPORT_YEARS,
  type ImportJob,
  type SecCompany,
  type SecFiling,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Step = "search" | "years" | "progress";

interface SecImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful import so the app can refresh and select the company. */
  onImported: (ticker: string) => void;
}

const message = (err: unknown) => (err instanceof Error ? err.message : "Something went wrong");

export function SecImportDialog({ open, onOpenChange, onImported }: SecImportDialogProps) {
  const [step, setStep] = useState<Step>("search");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SecCompany[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [company, setCompany] = useState<SecCompany | null>(null);
  const [filings, setFilings] = useState<SecFiling[]>([]);
  const [filingsLoading, setFilingsLoading] = useState(false);
  const [filingsError, setFilingsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  const [job, setJob] = useState<ImportJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStep("search");
    setQuery("");
    setResults([]);
    setSearchError(null);
    setCompany(null);
    setFilings([]);
    setFilingsError(null);
    setSelected([]);
    setJob(null);
    setJobError(null);
  }, []);

  // Debounced company search
  useEffect(() => {
    const q = query.trim();
    if (!q) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const payload = await api.secSearch(q, controller.signal);
        setResults(payload.results);
        setSearchError(null);
      } catch (err) {
        if (controller.signal.aborted) return;
        setSearchError(message(err));
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const onQueryChange = (value: string) => {
    setQuery(value);
    setSearchError(null);
    setSearching(value.trim().length > 0);
    if (!value.trim()) setResults([]);
  };

  const pickCompany = useCallback(async (picked: SecCompany) => {
    setCompany(picked);
    setStep("years");
    setFilings([]);
    setSelected([]);
    setFilingsError(null);
    setFilingsLoading(true);
    try {
      const payload = await api.secFilings(picked.ticker);
      setFilings(payload.filings);
    } catch (err) {
      setFilingsError(message(err));
    } finally {
      setFilingsLoading(false);
    }
  }, []);

  const toggleYear = (year: string) =>
    setSelected((current) =>
      current.includes(year)
        ? current.filter((y) => y !== year)
        : current.length < MAX_IMPORT_YEARS
          ? [...current, year]
          : current,
    );

  const startImport = useCallback(async () => {
    if (!company || selected.length === 0) return;
    setStep("progress");
    setJob(null);
    setJobError(null);
    try {
      setJob(await api.secImport(company.ticker, selected));
    } catch (err) {
      setJobError(message(err));
    }
  }, [company, selected]);

  // Poll the running job
  const jobId = job?.job_id;
  const jobActive = job?.status === "queued" || job?.status === "running";
  const failures = useRef(0);
  useEffect(() => {
    if (!jobId || !jobActive) return;
    failures.current = 0;
    const timer = setInterval(async () => {
      try {
        setJob(await api.secImportStatus(jobId));
        failures.current = 0;
      } catch (err) {
        if (++failures.current >= 5) {
          setJobError(message(err));
          clearInterval(timer);
        }
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [jobId, jobActive]);

  // Refresh the app as soon as a job completes — even if the dialog was hidden meanwhile.
  const notified = useRef<string | null>(null);
  const doneTicker = job?.status === "done" ? job.result?.ticker : undefined;
  useEffect(() => {
    if (!jobId || !doneTicker || notified.current === jobId) return;
    notified.current = jobId;
    onImported(doneTicker);
  }, [jobId, doneTicker, onImported]);

  const finish = () => onOpenChange(false);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next && !jobActive) setTimeout(reset, 200);
      }}
    >
      <DialogContent className="max-w-xl">
        {step === "search" && (
          <>
            <DialogHeader>
              <DialogTitle>Add a company from SEC EDGAR</DialogTitle>
              <DialogDescription>
                Search by company name or ticker, then choose which annual reports (10-K) to import.
              </DialogDescription>
            </DialogHeader>
            <div className="px-5 pb-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  autoFocus
                  aria-label="Search SEC companies"
                  value={query}
                  onChange={(event) => onQueryChange(event.target.value)}
                  placeholder="Try “Microsoft”, “NVDA” or “Tesla”"
                  className="h-11 w-full rounded-xl border bg-background pl-10 pr-10 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/20"
                />
                {searching && (
                  <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
                )}
              </div>
            </div>
            <div className="min-h-56 flex-1 overflow-y-auto px-3 pb-4">
              {searchError && (
                <p className="px-2 py-3 text-sm text-destructive">{searchError}</p>
              )}
              {!searchError && query.trim() && !searching && results.length === 0 && (
                <p className="px-2 py-8 text-center text-sm text-muted-foreground">
                  No SEC-listed company matches “{query.trim()}”.
                </p>
              )}
              {!query.trim() && (
                <p className="px-2 py-8 text-center text-sm text-muted-foreground">
                  Start typing to search every company registered with the SEC.
                </p>
              )}
              <ul className="space-y-1">
                {results.map((item) => (
                  <li key={`${item.ticker}-${item.cik}`}>
                    <button
                      onClick={() => void pickCompany(item)}
                      className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                    >
                      <TickerAvatar ticker={item.ticker} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{item.company_name}</span>
                        <span className="block text-xs text-muted-foreground">
                          {item.ticker} · CIK {item.cik}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}

        {step === "years" && company && (
          <>
            <DialogHeader>
              <button
                onClick={() => setStep("search")}
                className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="size-3" /> Back to search
              </button>
              <div className="flex items-center gap-3">
                <TickerAvatar ticker={company.ticker} />
                <div className="min-w-0">
                  <DialogTitle className="truncate">{company.company_name}</DialogTitle>
                  <DialogDescription>
                    Select up to {MAX_IMPORT_YEARS} fiscal years to import.
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>
            <div className="min-h-56 flex-1 overflow-y-auto px-5 pb-3">
              {filingsLoading && (
                <div className="space-y-2" aria-label="Loading filings">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="skeleton h-14 rounded-xl" />
                  ))}
                </div>
              )}
              {filingsError && (
                <p className="flex items-start gap-2 py-3 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  {filingsError}
                </p>
              )}
              <ul className="space-y-2">
                {filings.map((filing) => {
                  const checked = selected.includes(filing.fiscal_year);
                  const blocked = !checked && selected.length >= MAX_IMPORT_YEARS;
                  return (
                    <li key={filing.fiscal_year}>
                      <button
                        role="checkbox"
                        aria-checked={checked}
                        disabled={blocked}
                        onClick={() => toggleYear(filing.fiscal_year)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition-all focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                          checked
                            ? "border-primary bg-accent shadow-sm"
                            : "hover:border-primary/40 hover:bg-muted/60",
                          blocked && "cursor-not-allowed opacity-45 hover:border-border hover:bg-transparent",
                        )}
                      >
                        <span
                          className={cn(
                            "flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
                            checked ? "border-primary bg-primary text-primary-foreground" : "bg-background",
                          )}
                        >
                          {checked && <Check className="size-3.5" />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium">
                            {filing.fiscal_year} annual report
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            Filed {filing.filing_date}
                          </span>
                        </span>
                        {filing.indexed && (
                          <span className="rounded-full bg-success/15 px-2 py-0.5 text-[0.7rem] font-medium text-success">
                            Already indexed
                          </span>
                        )}
                        <a
                          href={filing.sec_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          aria-label={`Open ${filing.fiscal_year} filing on sec.gov`}
                          className="rounded-md p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                        >
                          <ExternalLink className="size-3.5" />
                        </a>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div className="flex items-center justify-between gap-3 border-t px-5 py-3">
              <span className="text-xs text-muted-foreground">
                {selected.length}/{MAX_IMPORT_YEARS} selected
                {selected.some((y) => filings.find((f) => f.fiscal_year === y)?.indexed) &&
                  " · already-indexed years are refreshed"}
              </span>
              <Button onClick={() => void startImport()} disabled={selected.length === 0}>
                Import {selected.length || ""} {selected.length === 1 ? "filing" : "filings"}
              </Button>
            </div>
          </>
        )}

        {step === "progress" && (
          <>
            <DialogHeader>
              <DialogTitle>
                {job?.status === "done"
                  ? "Import complete"
                  : job?.status === "error" || jobError
                    ? "Import failed"
                    : "Importing filings…"}
              </DialogTitle>
              <DialogDescription>
                {company?.company_name} · {selected.join(", ")}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 px-5 pb-5 pt-2">
              {!jobError && job?.status !== "error" && job?.status !== "done" && (
                <div className="space-y-3 rounded-xl border bg-muted/40 p-4">
                  <div className="flex items-center gap-3">
                    <Loader2 className="size-5 shrink-0 animate-spin text-primary" />
                    <p className="text-sm font-medium">{job?.message ?? "Starting…"}</p>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-border">
                    <div className="skeleton h-full w-full !bg-primary/60" />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    This usually takes 1–3 minutes per filing. You can keep this window open.
                    {job ? ` · ${Math.round(job.elapsed_s)}s elapsed` : ""}
                  </p>
                </div>
              )}
              {job?.status === "done" && job.result && (
                <div className="flex items-start gap-3 rounded-xl border border-success/30 bg-success/10 p-4">
                  <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" />
                  <p className="text-sm">
                    Indexed <b>{job.result.filing_count}</b> {job.result.filing_count === 1 ? "filing" : "filings"} (
                    {job.result.chunks} searchable excerpts) for <b>{job.result.company_name}</b>.
                  </p>
                </div>
              )}
              {(jobError || job?.status === "error") && (
                <div className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4">
                  <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" />
                  <p className="text-sm text-destructive">{jobError ?? job?.error}</p>
                </div>
              )}
              <div className="flex justify-end gap-2">
                {(jobError || job?.status === "error") && (
                  <Button variant="outline" onClick={() => setStep("years")}>
                    Back
                  </Button>
                )}
                {job?.status === "done" ? (
                  <Button onClick={finish}>Start chatting</Button>
                ) : (
                  jobActive && (
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>
                      Hide
                    </Button>
                  )
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
