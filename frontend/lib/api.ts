const BASE_URL = "/api";

export const UPLOAD_SCOPE = "__upload__";
export const MAX_IMPORT_YEARS = 2;

export interface Company {
  ticker: string;
  company_name: string;
  cik: string;
  form_types: string[];
  fiscal_years: string[];
  filing_count: number;
  chunk_count: number;
  legacy: boolean;
}

export interface Citation {
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

export interface AskResponse {
  answer: string;
  sources: string[];
  citations: Citation[];
}

export interface SecCompany {
  ticker: string;
  company_name: string;
  cik: string;
}

export interface SecFiling {
  fiscal_year: string;
  filing_date: string;
  sec_url: string;
  indexed: boolean;
}

export interface ImportJob {
  job_id: string;
  ticker: string;
  fiscal_years: string[];
  status: "queued" | "running" | "done" | "error";
  message: string;
  elapsed_s: number;
  error: string | null;
  result: { company_name: string; ticker: string; chunks: number; filing_count: number } | null;
}

export interface ClassifyResponse {
  category: string;
  available: boolean;
}

export interface UploadResponse {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  companies: () =>
    request<{ companies: Company[]; import_enabled: boolean }>("/companies"),
  ask: (question: string, ticker: string | null, year: string | null) =>
    request<AskResponse>("/ask", post({ question, ticker, year })),
  classify: (clause: string) => request<ClassifyResponse>("/classify", post({ clause })),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>("/upload", { method: "POST", body: form });
  },
  secSearch: (q: string, signal?: AbortSignal) =>
    request<{ results: SecCompany[] }>(`/sec/search?q=${encodeURIComponent(q)}`, { signal }),
  secFilings: (ticker: string) =>
    request<{ filings: SecFiling[]; max_years: number }>(
      `/sec/filings?ticker=${encodeURIComponent(ticker)}`,
    ),
  secImport: (ticker: string, fiscalYears: string[]) =>
    request<ImportJob>("/sec/import", post({ ticker, fiscal_years: fiscalYears })),
  secImportStatus: (jobId: string) => request<ImportJob>(`/sec/import/${jobId}`),
};
