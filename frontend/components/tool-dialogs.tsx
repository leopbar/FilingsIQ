"use client";

import { useRef, useState } from "react";
import { CheckCircle2, FileUp, Loader2, Scale } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api, type ClassifyResponse, type UploadResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const message = (err: unknown) => (err instanceof Error ? err.message : "Something went wrong");

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Manual PDF upload: Document Intelligence → PII redaction → chunk → embed → index. */
export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
}: DialogProps & { onUploaded: (result: UploadResponse) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<UploadResponse | null>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (next: File | null | undefined) => {
    setFile(next ?? null);
    setDone(null);
    setError(null);
  };

  const upload = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.upload(file);
      setDone(result);
      onUploaded(result);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload a PDF</DialogTitle>
          <DialogDescription>
            Index one temporary document with Document Intelligence and PII redaction, then chat with it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-5 pb-5">
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={(event) => pick(event.target.files?.[0])}
          />
          <button
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              pick(event.dataTransfer.files?.[0]);
            }}
            disabled={busy}
            className={cn(
              "flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              dragging ? "border-primary bg-accent" : "hover:border-primary/50 hover:bg-muted/50",
            )}
          >
            <FileUp className="size-7 text-primary" />
            <span className="text-sm font-medium">
              {file ? file.name : "Drop a PDF here, or click to browse"}
            </span>
            <span className="text-xs text-muted-foreground">
              {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "PDF only · up to 10 MB"}
            </span>
          </button>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {done && (
            <p className="flex items-start gap-2 text-sm text-success">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              {done.message} It is now selected in the sidebar.
            </p>
          )}
          <div className="flex justify-end gap-2">
            {done ? (
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            ) : (
              <Button onClick={() => void upload()} disabled={!file || busy}>
                {busy ? (
                  <>
                    <Loader2 className="animate-spin" /> Indexing…
                  </>
                ) : (
                  "Upload & index"
                )}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Fine-tuned GPT-4o classifier for contract clauses (41 CUAD categories). */
export function ClassifierDialog({ open, onOpenChange }: DialogProps) {
  const [clause, setClause] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClassifyResponse | null>(null);

  const classify = async () => {
    const value = clause.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.classify(value));
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Clause classifier</DialogTitle>
          <DialogDescription>
            A fine-tuned GPT-4o sorts legal contract clauses into 41 CUAD categories (77.5% accuracy).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-5 pb-5">
          <Textarea
            value={clause}
            onChange={(event) => setClause(event.target.value)}
            rows={5}
            className="resize-none"
            placeholder="Paste a legal contract clause…"
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          {result &&
            (result.available ? (
              <div className="flex items-center gap-3 rounded-xl border bg-muted/40 px-4 py-3">
                <Scale className="size-4 text-primary" />
                <span className="text-sm text-muted-foreground">Category</span>
                <Badge>{result.category}</Badge>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
                <b className="text-foreground">Classifier offline.</b> The fine-tuned deployment is
                stopped between demos to avoid hourly billing.
              </div>
            ))}
          <div className="flex justify-end">
            <Button onClick={() => void classify()} disabled={busy || !clause.trim()}>
              {busy ? (
                <>
                  <Loader2 className="animate-spin" /> Classifying…
                </>
              ) : (
                "Classify"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
