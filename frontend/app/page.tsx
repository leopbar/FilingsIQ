import FilingsClient, { type Company } from "./filings-client";

export const dynamic = "force-dynamic";

interface CompaniesPayload {
  companies: Company[];
  import_enabled: boolean;
}

export default async function Home() {
  const backendUrl = process.env.BACKEND_API_URL ?? "http://localhost:8000";
  let payload: CompaniesPayload = { companies: [], import_enabled: false };
  let error: string | null = null;

  try {
    const response = await fetch(`${backendUrl}/companies`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }
    payload = (await response.json()) as CompaniesPayload;
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "Could not load companies";
  }

  return (
    <FilingsClient
      initialCompanies={payload.companies}
      initialImportEnabled={payload.import_enabled}
      initialCompaniesError={error}
    />
  );
}
