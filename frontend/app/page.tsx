"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Building2, ChevronDown, ExternalLink, Loader2, Upload } from "lucide-react";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ASK_URL = `${BASE_URL}/ask`;
const COMPANIES_URL = `${BASE_URL}/companies`;
const IMPORT_URL = `${BASE_URL}/companies/import`;
const CLASSIFY_URL = `${BASE_URL}/classify`;
const UPLOAD_URL = `${BASE_URL}/upload`;
const UPLOAD_SCOPE = "__upload__";

interface Company {
  ticker: string;
  company_name: string;
  cik: string;
  form_types: string[];
  fiscal_years: string[];
  filing_count: number;
  chunk_count: number;
  legacy: boolean;
}

interface Citation {
  source_number: number;
  ticker: string;
  company_name: string;
  form_type: string;
  fiscal_year: string;
  filing_date: string;
  accession_number: string;
  sec_url: string;
  title: string;
}

interface AskResponse {
  answer: string;
  sources: string[];
  citations: Citation[];
}

interface ImportResponse {
  ticker: string;
  company_name: string;
  filing_count: number;
  chunks: number;
  replaced_chunks: number;
}

interface ClassifyResponse {
  category: string;
  available: boolean;
}

interface UploadResponse {
  filename: string;
  chunks: number;
  message: string;
}

async function errorMessage(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const payload = JSON.parse(text) as { detail?: string };
    return payload.detail ?? text;
  } catch {
    return text || `Request failed with status ${response.status}`;
  }
}

export default function Home() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesError, setCompaniesError] = useState<string | null>(null);
  const [importEnabled, setImportEnabled] = useState(false);
  const [ticker, setTicker] = useState("");
  const [year, setYear] = useState("all");

  const [importTicker, setImportTicker] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [clause, setClause] = useState("");
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyResult, setClassifyResult] = useState<ClassifyResponse | null>(null);
  const [classifyError, setClassifyError] = useState<string | null>(null);

  const selectedCompany = useMemo(
    () => companies.find((company) => company.ticker === ticker),
    [companies, ticker],
  );

  const loadCompanies = useCallback(async () => {
    setCompaniesLoading(true);
    setCompaniesError(null);
    try {
      const response = await fetch(COMPANIES_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(await errorMessage(response));
      const payload = (await response.json()) as { companies: Company[]; import_enabled: boolean };
      setCompanies(payload.companies);
      setImportEnabled(payload.import_enabled);
      setTicker((current) => {
        if (current === UPLOAD_SCOPE || payload.companies.some((company) => company.ticker === current)) {
          return current;
        }
        return payload.companies.find((company) => company.ticker === "AAPL")?.ticker
          ?? payload.companies[0]?.ticker
          ?? "";
      });
    } catch (err) {
      setCompaniesError(err instanceof Error ? err.message : "Could not load companies");
    } finally {
      setCompaniesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCompanies();
  }, [loadCompanies]);

  const handleImport = useCallback(async () => {
    const normalized = importTicker.trim().toUpperCase();
    if (!normalized || importing) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const response = await fetch(IMPORT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: normalized }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const payload = (await response.json()) as ImportResponse;
      setImportResult(payload);
      setImportTicker("");
      await loadCompanies();
      setTicker(payload.ticker);
      setYear("all");
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Company import failed");
    } finally {
      setImporting(false);
    }
  }, [importTicker, importing, loadCompanies]);

  const ask = useCallback(async () => {
    const q = question.trim();
    if (!q || loading || !ticker) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setSourcesOpen(false);
    try {
      const uploadedDocument = ticker === UPLOAD_SCOPE;
      const response = await fetch(ASK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          ticker: uploadedDocument ? null : ticker,
          year: uploadedDocument ? "upload" : year === "all" ? null : year,
        }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      setResult((await response.json()) as AskResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [question, loading, ticker, year]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile || uploading) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      const response = await fetch(UPLOAD_URL, { method: "POST", body: form });
      if (!response.ok) throw new Error(await errorMessage(response));
      setUploadResult((await response.json()) as UploadResponse);
      setTicker(UPLOAD_SCOPE);
      setYear("all");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setUploading(false);
    }
  }, [selectedFile, uploading]);

  const classify = useCallback(async () => {
    const value = clause.trim();
    if (!value || classifyLoading) return;
    setClassifyLoading(true);
    setClassifyResult(null);
    setClassifyError(null);
    try {
      const response = await fetch(CLASSIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clause: value }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      setClassifyResult((await response.json()) as ClassifyResponse);
    } catch (err) {
      setClassifyError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setClassifyLoading(false);
    }
  }, [clause, classifyLoading]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-card/80 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 py-4">
          <h1 className="text-xl font-semibold tracking-tight">FilingsIQ</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            AI-powered chat with SEC filings · Company-scoped answers · Filing citations
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-5 px-4 py-8">
        {importEnabled && <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Building2 className="h-4 w-4" /> Add an SEC company
            </CardTitle>
            <CardDescription>
              Enter a ticker to download and index its five latest 10-K filings from SEC EDGAR.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <input
                aria-label="Company ticker"
                value={importTicker}
                onChange={(event) => setImportTicker(event.target.value.toUpperCase())}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void handleImport();
                }}
                placeholder="MSFT"
                maxLength={10}
                disabled={importing}
                className="h-9 min-w-0 flex-1 rounded-md border bg-transparent px-3 text-sm uppercase outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
              />
              <Button onClick={handleImport} disabled={importing || !importTicker.trim()} size="sm">
                {importing ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Importing…</> : "Import filings"}
              </Button>
            </div>
            {importing && (
              <p className="text-xs text-muted-foreground">
                Downloading, chunking, and embedding five filings. This can take several minutes.
              </p>
            )}
            {importError && <p className="text-sm text-destructive"><b>Error:</b> {importError}</p>}
            {importResult && (
              <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-300">
                ✓ Indexed {importResult.filing_count} filings and {importResult.chunks} chunks for {importResult.company_name} ({importResult.ticker}).
              </div>
            )}
          </CardContent>
        </Card>}

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Ask a question</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Company:</span>
              <Select
                value={ticker}
                onValueChange={(value) => { setTicker(value ?? ""); setYear("all"); }}
                disabled={companiesLoading}
              >
                <SelectTrigger className="h-8 w-64 text-xs"><SelectValue placeholder="Select a company" /></SelectTrigger>
                <SelectContent>
                  {companies.map((company) => (
                    <SelectItem key={company.ticker} value={company.ticker}>
                      {company.ticker} · {company.company_name}
                    </SelectItem>
                  ))}
                  {uploadResult && <SelectItem value={UPLOAD_SCOPE}>Uploaded document</SelectItem>}
                </SelectContent>
              </Select>

              {ticker !== UPLOAD_SCOPE && (
                <>
                  <span className="ml-1 text-xs text-muted-foreground">Year:</span>
                  <Select value={year} onValueChange={(value) => setYear(value ?? "all")}>
                    <SelectTrigger className="h-8 w-32 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All years</SelectItem>
                      {(selectedCompany?.fiscal_years ?? []).map((fiscalYear) => (
                        <SelectItem key={fiscalYear} value={fiscalYear}>{fiscalYear}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </>
              )}
            </div>

            {selectedCompany && (
              <p className="text-xs text-muted-foreground">
                {selectedCompany.filing_count} filings · {selectedCompany.chunk_count} searchable excerpts
                {selectedCompany.legacy ? " · Apple metadata migration pending" : ""}
              </p>
            )}
            {companiesError && <p className="text-xs text-destructive">Could not load companies: {companiesError}</p>}

            <Textarea
              placeholder={selectedCompany ? `Ask about ${selectedCompany.company_name}…` : "Select or import a company first"}
              rows={3}
              className="resize-none"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); }
              }}
              disabled={loading || !ticker}
            />
            <div className="flex justify-end">
              <Button onClick={ask} disabled={loading || !question.trim() || !ticker} size="sm">
                {loading ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Thinking…</> : "Ask"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {error && (
          <Card className="border-destructive/40 bg-destructive/5"><CardContent className="pt-5">
            <p className="text-sm text-destructive"><b>Error:</b> {error}</p>
          </CardContent></Card>
        )}

        {result && (
          <>
            <Card><CardHeader><CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Answer</CardTitle></CardHeader>
              <CardContent><p className="whitespace-pre-wrap text-sm leading-relaxed">{result.answer}</p></CardContent>
            </Card>
            {result.sources.length > 0 && (
              <Card>
                <button onClick={() => setSourcesOpen((open) => !open)} className="w-full rounded-t-xl px-4 py-3 text-left transition-colors hover:bg-muted/50">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Sources</span>
                    <div className="flex items-center gap-2"><Badge variant="secondary">{result.sources.length} excerpts</Badge>
                      <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${sourcesOpen ? "rotate-180" : ""}`} />
                    </div>
                  </div>
                </button>
                {sourcesOpen && (
                  <div className="space-y-5 border-t px-4 pb-4 pt-4">
                    {result.sources.map((source, index) => {
                      const citation = result.citations?.[index];
                      return (
                        <div key={index} className="flex gap-3">
                          <Badge variant="outline" className="mt-0.5 shrink-0 font-mono">{index + 1}</Badge>
                          <div className="min-w-0 space-y-1.5">
                            {citation && (
                              <div className="flex flex-wrap items-center gap-2 text-xs">
                                <span className="font-medium text-foreground">{citation.title}</span>
                                {citation.filing_date && <span className="text-muted-foreground">Filed {citation.filing_date}</span>}
                                {citation.sec_url && (
                                  <a href={citation.sec_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                                    SEC filing <ExternalLink className="h-3 w-3" />
                                  </a>
                                )}
                              </div>
                            )}
                            <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{source.trim()}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
            )}
          </>
        )}

        <div className="border-t pt-2" />
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Upload a PDF</CardTitle>
            <CardDescription>Index one temporary document with Document Intelligence and PII redaction.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={(event) => {
              setSelectedFile(event.target.files?.[0] ?? null); setUploadResult(null); setUploadError(null);
            }} />
            <div className="flex items-center gap-3">
              <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>Choose file</Button>
              <span className="max-w-[200px] truncate text-xs text-muted-foreground">{selectedFile?.name ?? "No file chosen"}</span>
              <Button size="sm" onClick={handleUpload} disabled={uploading || !selectedFile} className="ml-auto">
                {uploading ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Indexing…</> : <><Upload className="mr-1.5 h-3.5 w-3.5" />Upload &amp; Index</>}
              </Button>
            </div>
            {uploadError && <p className="text-sm text-destructive"><b>Error:</b> {uploadError}</p>}
            {uploadResult && <p className="text-xs text-green-700 dark:text-green-300">✓ {uploadResult.message} The uploaded document is now selected.</p>}
          </CardContent>
        </Card>

        <div className="border-t pt-2" />
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Clause Classifier</CardTitle>
            <CardDescription>Fine-tuned GPT-4o classifies legal contract clauses into 41 CUAD categories.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea value={clause} onChange={(event) => setClause(event.target.value)} rows={4} className="resize-none" placeholder="Paste a legal contract clause…" />
            <div className="flex justify-end"><Button onClick={classify} disabled={classifyLoading || !clause.trim()} size="sm" variant="secondary">
              {classifyLoading ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Classifying…</> : "Classify"}
            </Button></div>
            {classifyError && <p className="text-sm text-destructive"><b>Error:</b> {classifyError}</p>}
            {classifyResult && (classifyResult.available
              ? <div className="rounded-lg border bg-muted/40 px-4 py-3"><Badge>{classifyResult.category}</Badge></div>
              : <div className="rounded-lg border border-dashed px-4 py-3 text-xs text-muted-foreground"><b className="text-foreground">Classifier offline.</b> The fine-tuned deployment is stopped between demos to avoid hourly billing.</div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
