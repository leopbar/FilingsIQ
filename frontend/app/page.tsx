"use client";

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronDown, Loader2, Upload } from "lucide-react";

const BASE_URL     = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ASK_URL      = `${BASE_URL}/ask`;
const CLASSIFY_URL = `${BASE_URL}/classify`;
const UPLOAD_URL   = `${BASE_URL}/upload`;

const FISCAL_YEARS = ["FY2025", "FY2024", "FY2023", "FY2022", "FY2021"];

interface AskResponse {
  answer: string;
  sources: string[];
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

export default function Home() {
  // ── chat state ──────────────────────────────────────────────────────────────
  const [question, setQuestion] = useState("");
  const [year, setYear] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  // ── upload state ────────────────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // ── classifier state ────────────────────────────────────────────────────────
  const [clause, setClause] = useState("");
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyResult, setClassifyResult] = useState<ClassifyResponse | null>(null);
  const [classifyError, setClassifyError] = useState<string | null>(null);

  // ── chat handlers ───────────────────────────────────────────────────────────
  const ask = useCallback(async () => {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setSourcesOpen(false);
    try {
      const res = await fetch(ASK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, year: year === "all" ? null : year }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend returned ${res.status}: ${text}`);
      }
      const data: AskResponse = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [question, year, loading]);

  const handleAskKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  };

  // ── upload handlers ─────────────────────────────────────────────────────────
  const handleUpload = useCallback(async () => {
    if (!selectedFile || uploading) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      const res = await fetch(UPLOAD_URL, { method: "POST", body: form });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend returned ${res.status}: ${text}`);
      }
      const data: UploadResponse = await res.json();
      setUploadResult(data);
      setYear("upload");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setUploading(false);
    }
  }, [selectedFile, uploading]);

  // ── classifier handlers ─────────────────────────────────────────────────────
  const classify = useCallback(async () => {
    const c = clause.trim();
    if (!c || classifyLoading) return;
    setClassifyLoading(true);
    setClassifyResult(null);
    setClassifyError(null);
    try {
      const res = await fetch(CLASSIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clause: c }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend returned ${res.status}: ${text}`);
      }
      const data: ClassifyResponse = await res.json();
      setClassifyResult(data);
    } catch (err) {
      setClassifyError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setClassifyLoading(false);
    }
  }, [clause, classifyLoading]);

  const handleClassifyKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      classify();
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-card/80 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 py-4">
          <h1 className="text-xl font-semibold tracking-tight">FilingsIQ</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            AI-powered chat with Apple SEC filings · Grounded answers · No hallucinations
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-5 px-4 py-8">

        {/* ── Chat ──────────────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Ask a question
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Filing year:</span>
              <Select value={year} onValueChange={(v) => setYear(v ?? "all")}>
                <SelectTrigger className="h-8 w-44 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All years</SelectItem>
                  {FISCAL_YEARS.map((fy) => (
                    <SelectItem key={fy} value={fy}>{fy}</SelectItem>
                  ))}
                  {uploadResult && (
                    <SelectItem value="upload">
                      Uploaded doc
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <Textarea
              placeholder="e.g. What were Apple's total net sales in fiscal 2025?"
              rows={3}
              className="resize-none"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleAskKeyDown}
              disabled={loading}
            />
            <div className="flex justify-end">
              <Button onClick={ask} disabled={loading || !question.trim()} size="sm">
                {loading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Thinking…
                  </>
                ) : (
                  "Ask"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Error */}
        {error && (
          <Card className="border-destructive/40 bg-destructive/5">
            <CardContent className="pt-5">
              <p className="text-sm text-destructive">
                <span className="font-semibold">Error:</span> {error}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Answer */}
        {result && (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Answer
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {result.answer}
                </p>
              </CardContent>
            </Card>

            {result.sources.length > 0 && (
              <Card>
                <button
                  onClick={() => setSourcesOpen((o) => !o)}
                  className="w-full rounded-t-xl px-4 py-3 text-left transition-colors hover:bg-muted/50"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Sources
                    </span>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{result.sources.length} excerpts</Badge>
                      <ChevronDown
                        className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
                          sourcesOpen ? "rotate-180" : ""
                        }`}
                      />
                    </div>
                  </div>
                </button>
                {sourcesOpen && (
                  <div className="space-y-4 border-t px-4 pb-4 pt-4">
                    {result.sources.map((src, i) => (
                      <div key={i} className="flex gap-3">
                        <Badge variant="outline" className="mt-0.5 shrink-0 font-mono">
                          {i + 1}
                        </Badge>
                        <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
                          {src.trim()}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}
          </>
        )}

        <div className="border-t pt-2" />

        {/* ── PDF Upload ────────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Upload a PDF</CardTitle>
            <CardDescription>
              Index any PDF to chat with it · Document Intelligence extracts text + tables · PII is redacted · Select &quot;Uploaded doc&quot; in the year filter above to query it
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setSelectedFile(f);
                setUploadResult(null);
                setUploadError(null);
              }}
            />

            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                Choose file
              </Button>
              <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                {selectedFile ? selectedFile.name : "No file chosen"}
              </span>
              <Button
                size="sm"
                onClick={handleUpload}
                disabled={uploading || !selectedFile}
                className="ml-auto"
              >
                {uploading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Indexing…
                  </>
                ) : (
                  <>
                    <Upload className="mr-1.5 h-3.5 w-3.5" />
                    Upload &amp; Index
                  </>
                )}
              </Button>
            </div>

            {uploading && (
              <p className="text-xs text-muted-foreground">
                Processing — Document Intelligence is extracting text and tables. This takes 30–90 seconds depending on file size…
              </p>
            )}

            {uploadError && (
              <p className="text-sm text-destructive">
                <span className="font-semibold">Error:</span> {uploadError}
              </p>
            )}

            {uploadResult && (
              <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-900 dark:bg-green-950/30">
                <span className="text-xs text-green-800 dark:text-green-300">
                  ✓ {uploadResult.message} — &quot;Uploaded doc&quot; is now available in the year filter.
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="border-t pt-2" />

        {/* ── Clause Classifier ─────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Clause Classifier</CardTitle>
            <CardDescription>
              Paste a legal contract clause · fine-tuned GPT-4o identifies its CUAD category (41 types · 77.5% accuracy vs 17.7% zero-shot)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              placeholder="e.g. Either party may terminate this Agreement upon 30 days written notice..."
              rows={4}
              className="resize-none"
              value={clause}
              onChange={(e) => setClause(e.target.value)}
              onKeyDown={handleClassifyKeyDown}
              disabled={classifyLoading}
            />
            <div className="flex justify-end">
              <Button
                onClick={classify}
                disabled={classifyLoading || !clause.trim()}
                size="sm"
                variant="secondary"
              >
                {classifyLoading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Classifying…
                  </>
                ) : (
                  "Classify"
                )}
              </Button>
            </div>

            {classifyError && (
              <p className="text-sm text-destructive">
                <span className="font-semibold">Error:</span> {classifyError}
              </p>
            )}

            {classifyResult && (
              classifyResult.available ? (
                <div className="rounded-lg border bg-muted/40 px-4 py-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Category
                  </p>
                  <Badge className="text-sm">{classifyResult.category}</Badge>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed px-4 py-3">
                  <p className="text-xs text-muted-foreground">
                    <span className="font-semibold text-foreground">Classifier offline.</span>{" "}
                    The fine-tuned model deployment is spun down between demos to avoid hourly
                    billing. To enable: deploy{" "}
                    <span className="font-mono text-xs">ft-cuad-classifier</span> in Azure
                    OpenAI Studio, then retry.
                  </p>
                </div>
              )
            )}
          </CardContent>
        </Card>

      </main>
    </div>
  );
}
